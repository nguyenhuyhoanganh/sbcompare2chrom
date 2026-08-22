"""Semantic diff between two snapshots.

The whole point of this stage is to answer "what actually changed" rather than
"what text differs".  Two rules do most of that work:

1. **Attribute whitelists.**  Only attributes whose movement means something
   are compared.  Between M139 and M143 every ``BASE_FEATURE`` in the tree
   changed its declaration syntax; comparing a ``declared_form`` attribute
   would emit thousands of modifications that mean nothing to anyone.

2. **Platform-aware verdicts.**  A default flip is scored for Windows, the
   one platform this desktop product ships.  Chromium wraps many defaults in
   ``#if BUILDFLAG(IS_WIN)`` chains, so the global value and the shipped value
   routinely disagree; reading the wrong one inverts the conclusion.

Rename detection runs as a post-pass for switches and prefs, whose identity is
the string value itself: a renamed pref would otherwise appear as an unrelated
removal plus addition, hiding the fact that stored user data is orphaned.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .extract._cpp import PLATFORM
from .extract.blink_runtime import status_rank
from .model import (
    OWNER_NATIVE,
    OWNER_CONFIG,
    KIND_OWNERS,
    ADDED,
    BUCKET_BEHAVIOUR,
    BUCKET_BREAKING,
    BUCKET_HOUSEKEEPING,
    BUCKET_NEW,
    KIND_BASE_FEATURE,
    KIND_BLINK_RUNTIME,
    KIND_FEATURE_PARAM,
    KIND_FLAG_ENTRY,
    KIND_IDL_INTERFACE,
    KIND_IDL_MEMBER,
    KIND_MOJO_ENUM,
    KIND_MOJO_FIELD,
    KIND_MOJO_INTERFACE,
    KIND_MOJO_METHOD,
    KIND_MOJO_STRUCT,
    KIND_PREF,
    KIND_SWITCH,
    KIND_WEBUI_CONTROL,
    KIND_WEBUI_GATE,
    KIND_WEBUI_ROUTE,
    MODIFIED,
    REMOVED,
    Change,
    Fact,
    Snapshot,
)

# Attributes whose change carries meaning.  Anything outside this list is
# treated as bookkeeping.
MEANINGFUL_ATTRS: Dict[str, Tuple[str, ...]] = {
    # "conditions" matters because a declaration can be moved into or out of
    # a build without its value changing at all: the guard appearing or
    # disappearing is the change, while the value stays identical.
    # "var" is the C++ identifier. Code writes `features::kFoo`, never the
    # feature string, so renaming the identifier while keeping the string
    # breaks a build -- and the string is what this fact is keyed on, so
    # without comparing "var" the change produces no finding at all.
    # Measured M130 -> M151: 4 such renames, including kDIPS -> kBtm.
    KIND_BASE_FEATURE: ("default_state", "platform_state", "conditions", "var"),
    KIND_FEATURE_PARAM: ("default", "type", "feature", "var", "platform_state"),
    KIND_BLINK_RUNTIME: (
        "status", "platform_status", "windows_status", "base_feature",
        "base_feature_status", "origin_trial_feature_name", "depends_on",
        "implied_by", "public", "copied_from_base_feature_if",
        # Origin-trial and internals wiring. Measured M130 -> M151:
        # origin_trial_allows_third_party moves 36 times, the other three once
        # each. They decide who can turn a feature on from outside the binary,
        # so a move is a change in reach, not bookkeeping.
        "origin_trial_allows_third_party", "settable_from_internals",
        "browser_process_read_access", "browser_process_read_write_access",
        # Which operating systems the trial runs on, which kind of trial it is,
        # whether it works without HTTPS, and whether the flag is protected
        # from being forced. Same job as the four above: they decide who can
        # reach the feature from outside the binary.
        "origin_trial_os", "origin_trial_type", "origin_trial_allows_insecure",
        "is_protected_feature",
    ),
    KIND_IDL_INTERFACE: ("idl_kind", "inherits", "ext", "values"),
    KIND_IDL_MEMBER: ("signature", "signatures", "overload_traits",
                      "member_type", "ext", "runtime_enabled"),
    # Empty, and deliberately. "methods" and "method_count" do change -- 107
    # times across M130 -> M151 -- but every one of those is already a
    # mojo_method added or removed finding of its own, so comparing them here
    # would report the same ABI change twice, once vaguely and once precisely.
    # "module" used to sit here to keep the tuple non-empty, which was worse
    # than empty: it is part of the key, so it can never differ, and it read as
    # an attribute that could move and produce a row nothing explains. An
    # interface's identity moving *is* an add plus a remove.
    KIND_MOJO_INTERFACE: ("stable", "platform_state"),
    # `ordinal` is wire order. `Foo@0` and `Foo@1` are the same declaration to
    # every other field here and a different message on the wire, so leaving it
    # out made an ABI change produce no row at all. It was extracted and then
    # not compared -- the two halves of this pipeline are separate doors, and
    # opening the first is not opening the second.
    KIND_MOJO_METHOD: ("signature", "params", "response", "attrs", "ordinal",
                       "position", "stable", "platform_state",
                       "inherited_conditions"),
    # `fields` is left out for the reason `methods` is left out above: every
    # field is a fact of its own, so comparing the list reports one ABI change
    # twice. `mojo_kind` can move -- a struct becoming a union is a different
    # wire format under the same name.
    KIND_MOJO_STRUCT: ("mojo_kind", "stable", "platform_state"),
    # The type and the ordinal are the wire format. The default and the
    # `[MinVersion]` annotation are not, and they are labelled separately.
    KIND_MOJO_FIELD: ("type", "ordinal", "default", "attrs", "position",
                      "min_version", "stable", "platform_state",
                      "inherited_conditions"),
    # One list rather than a fact per member: members are 17,061 of the tree's
    # declarations at M151, and adding one is Mojo's ordinary way of extending
    # a type.
    KIND_MOJO_ENUM: ("values", "stable", "platform_state"),
    # "platform_state" is the guard resolved for Windows, not the guard text:
    # a key entering or leaving our binary is the change, while Chromium
    # tidying `!IS_ANDROID` off one is not. The raw `conditions` stay on the
    # fact, unread here, because a reader may want the guard text itself.
    KIND_SWITCH: ("var", "platform_state"),
    KIND_PREF: ("var", "platform_state"),
    KIND_FLAG_ENTRY: ("expiry_milestone",),
    KIND_WEBUI_ROUTE: ("route", "parent", "guards"),
    KIND_WEBUI_CONTROL: ("control", "pref", "label", "build_conditions",
                         "platform_state"),
    KIND_WEBUI_GATE: ("expression", "features", "enabled_checks"),
}

# Severity per (kind, change_type), used **only when a change carries no
# signal at all**.  It is the coarse prior: "a Mojo method appeared" is the
# whole story when nothing more precise can be said about it.
#
# It used to be a floor under the signal instead, and the floor won whenever it
# was higher -- which is exactly when it was wrong, because the signal is the
# precise statement and this is the guess.  A Mojo method whose mojom
# attributes moved scored 75, the same as one whose signature moved, because
# `(mojo_method, modified)` is 75 and `build_gate_changed` is 35.
BASE_SEVERITY: Dict[Tuple[str, str], int] = {
    (KIND_IDL_INTERFACE, REMOVED): 70,
    (KIND_IDL_INTERFACE, ADDED): 30,
    (KIND_IDL_INTERFACE, MODIFIED): 40,
    (KIND_IDL_MEMBER, REMOVED): 60,
    (KIND_IDL_MEMBER, ADDED): 25,
    (KIND_IDL_MEMBER, MODIFIED): 45,
    (KIND_MOJO_INTERFACE, REMOVED): 70,
    (KIND_MOJO_INTERFACE, ADDED): 20,
    (KIND_MOJO_INTERFACE, MODIFIED): 40,
    (KIND_MOJO_METHOD, REMOVED): 70,
    (KIND_MOJO_METHOD, ADDED): 20,
    (KIND_MOJO_METHOD, MODIFIED): 75,
    (KIND_MOJO_STRUCT, REMOVED): 70,
    (KIND_MOJO_STRUCT, ADDED): 20,
    (KIND_MOJO_STRUCT, MODIFIED): 60,
    (KIND_MOJO_FIELD, REMOVED): 70,
    (KIND_MOJO_FIELD, ADDED): 20,
    (KIND_MOJO_FIELD, MODIFIED): 60,
    (KIND_MOJO_ENUM, REMOVED): 65,
    (KIND_MOJO_ENUM, ADDED): 20,
    (KIND_MOJO_ENUM, MODIFIED): 45,
    # Retirement is the common case, so the floor comes from the signal:
    # flag_retired_on/off stay low, feature_deleted (state unknown) stays high.
    (KIND_BASE_FEATURE, REMOVED): 30,
    (KIND_BASE_FEATURE, ADDED): 20,
    (KIND_BASE_FEATURE, MODIFIED): 45,
    (KIND_FEATURE_PARAM, REMOVED): 35,
    (KIND_FEATURE_PARAM, ADDED): 15,
    (KIND_FEATURE_PARAM, MODIFIED): 35,
    (KIND_BLINK_RUNTIME, REMOVED): 20,
    (KIND_BLINK_RUNTIME, ADDED): 25,
    (KIND_BLINK_RUNTIME, MODIFIED): 40,
    (KIND_SWITCH, REMOVED): 30,
    (KIND_SWITCH, ADDED): 10,
    (KIND_SWITCH, MODIFIED): 40,
    (KIND_PREF, REMOVED): 35,
    (KIND_PREF, ADDED): 10,
    (KIND_PREF, MODIFIED): 45,
    (KIND_FLAG_ENTRY, REMOVED): 30,
    (KIND_FLAG_ENTRY, ADDED): 5,
    (KIND_FLAG_ENTRY, MODIFIED): 15,
    (KIND_WEBUI_ROUTE, REMOVED): 55,
    (KIND_WEBUI_ROUTE, ADDED): 40,
    (KIND_WEBUI_ROUTE, MODIFIED): 45,
    (KIND_WEBUI_CONTROL, REMOVED): 35,
    (KIND_WEBUI_CONTROL, ADDED): 25,
    (KIND_WEBUI_CONTROL, MODIFIED): 30,
    (KIND_WEBUI_GATE, REMOVED): 40,
    (KIND_WEBUI_GATE, ADDED): 25,
    (KIND_WEBUI_GATE, MODIFIED): 45,
}

# Signals are the human-readable "why this matters" labels, with a severity
# floor.  A change keeps the highest floor among its signals.
SIGNAL_SEVERITY: Dict[str, int] = {
    "enabled_by_default": 75,
    "disabled_by_default": 60,
    "default_flip_on": 60,
    "default_flip_off": 50,
    "feature_deleted": 65,
    "flag_retired_on": 35,
    "flag_retired_off": 30,
    "new_feature_on_by_default": 55,
    "web_api_shipped": 65,
    "web_api_unshipped": 70,
    "web_api_removed": 70,
    "web_api_added": 30,
    # Split by whether a page can reach it. 133 of 220 additions at
    # M148 -> M151 are live on arrival and 87 are still behind a closed gate;
    # they used to score the same. `web_api_added` stays for the case the run
    # cannot decide, at the severity both used to get.
    "web_api_added_live": 35,
    "web_api_added_gated": 20,
    # Removing what no page could reach is the web API spelling of
    # `flag_retired_off`, and carries its severity and its bucket.
    "web_api_removed_gated": 30,
    "killswitch_retired": 35,
    "experimental_dropped": 20,
    "web_api_signature_change": 50,
    # An overload set losing a member is a callable shape disappearing: any
    # site passing that argument list stops matching. Below a whole-member
    # removal at 70 because the name still resolves.
    "web_api_overload_removed": 60,
    # Gaining one breaks nothing -- every existing call still matches the
    # overload it always did -- so it is new surface, not a contract move.
    "web_api_overload_added": 25,
    # A new overload taking an argument count an existing one already takes.
    # Resolution picks by count first, so a call that used to reach the older
    # one can now reach this instead -- no removal, no signature change, and
    # the site is unedited.
    "web_api_overload_shadowed": 45,
    "ipc_signature_change": 80,
    "ipc_removed": 75,
    # The data half of the same break. A field changing type or ordinal means
    # the other process reads those bytes as something else, and a struct
    # becoming a union changes the wire format under an unchanged name.
    "ipc_shape_changed": 80,
    # A method's ordinal is how a peer decides which method it is being
    # called. Changing it does not break the build and does not change the
    # signature; the far side simply runs a different method, or rejects the
    # message. Same weight as a changed signature for that reason.
    "ipc_ordinal_changed": 80,
    # An enum gaining or losing a member. Not the same severity: adding one is
    # how Mojo extends a type, and the receiver that has to be taught about it
    # rejects the message rather than misreading it.
    "ipc_enum_changed": 55,
    # The default value or the `[MinVersion]` annotation moved. Neither changes
    # how the bytes are read; both change what an older peer sees.
    "ipc_field_annotated": 35,
    # `[Stable]` appearing means Chromium has begun promising this shape;
    # disappearing means it has stopped. Neither moves a byte today, and both
    # decide whether every later move is a break.
    "ipc_stability_changed": 40,
    "pref_renamed": 70,
    "switch_renamed": 60,
    # A pref or switch that simply stops appearing is *not* evidence that
    # Chromium deleted it. Measured at M151: 100 non-ChromeOS `pref_names`
    # files exist and this tool reads one of them, so a key leaving
    # chrome/common/pref_names.h is at least as likely to have moved into a
    # file outside the scan. Chromium is actively splitting that file up --
    # 4,322 lines at M143, 3,267 at M151 -- which turned 337 such moves into
    # 337 "removed" findings at severity 55 across two uprevs.
    #
    # The honest severity is lower than a confirmed removal and higher than
    # nothing, because the one case that would matter is real and invisible.
    # A *rename*, by contrast, is confirmed evidence (the C++ variable pairs
    # the two sides), so it keeps its high floor above.
    "pref_left_scan": 35,
    "switch_left_scan": 30,
    "feature_string_renamed": 75,
    # The mirror image of feature_string_renamed: there the string moved and the
    # identifier held; here the identifier moved and the string held. That one
    # fails silently in Finch configs, this one fails loudly at build time --
    # but only after the merge, which is exactly what the tool exists to move
    # earlier.
    "feature_symbol_renamed": 60,
    # The same pair, one level down, for the two kinds whose identity is also a
    # string. A renamed pref *key* orphans stored user data (70); a renamed C++
    # constant for that key does not touch the data at all, it breaks our build
    # after the merge -- the same fifteen-point gap the base::Feature pair uses.
    "pref_symbol_renamed": 55,
    "switch_symbol_renamed": 45,
    "declaration_moved": 25,
    "ui_page_removed": 55,
    "ui_page_added": 40,
    "ui_page_regated": 45,
    "ui_page_moved": 30,
    "ui_control_type_changed": 45,
    "ui_control_repointed": 50,
    "ui_control_removed": 35,
    "ui_control_added": 25,
    "ui_gate_changed": 45,
    "ui_gate_removed": 40,
    "ui_gate_added": 25,
    "param_default_changed": 40,
    # The knob itself is gone. A Finch config or a command line that still sets
    # it silently stops having any effect, which is the same shape of failure a
    # renamed feature string has -- and until now it was the largest kind of
    # change in a report that produced no label at all: 53 of the 903
    # unlabelled findings at M148 -> M151.
    "param_removed": 35,
    # The knob itself moved rather than its value: a different C++ type, or a
    # different owning flag. Both were compared and neither produced a row
    # anyone could read.
    "param_rewired": 35,
    "flag_expiring": 45,
    # Below the kind's own base severity of 15, so labelling these changes no
    # ranking. They are the largest single group in a report -- 281 at
    # M148 -> M151, 300 on an earlier one -- and they are a scheduling change
    # on a settings page, not a feature change. The point is only that a row
    # the tool chose to emit should say what moved.
    "flag_expiry_moved": 10,
    "origin_trial_change": 35,
    # These attributes were compared and then never explained. A row with a
    # severity and an empty reason column is worse than no row: the reader has
    # to open the source to find out what moved. Measured M148 -> M151, 99
    # modified changes arrived that way.
    "web_api_exposure_changed": 45,
    "web_api_shape_changed": 45,
    "web_api_status_moved": 25,
    "runtime_flag_rewired": 30,
    "build_gate_changed": 35,
    "ui_control_relabelled": 20,
}

SIGNAL_LABELS: Dict[str, str] = {
    "enabled_by_default": "Now ON by default on Windows",
    "disabled_by_default": "Now OFF by default on Windows",
    "default_flip_on": "Default flipped on",
    "default_flip_off": "Default flipped off",
    "feature_deleted": "Feature flag deleted, prior state unreadable",
    "flag_retired_on": "Shipped, then flag retired — behaviour is now permanent "
                       "and can no longer be turned off",
    "flag_retired_off": "Never shipped, flag and code removed — can no longer "
                        "be turned on",
    "new_feature_on_by_default": "New feature, on by default",
    "web_api_shipped": "Web API reached stable",
    "web_api_unshipped": "Web API pulled back from stable",
    "web_api_removed": "Web API removed",
    "web_api_added": "New web API surface",
    "web_api_added_live": "New web API, reachable by a page now",
    "web_api_added_gated": "New web API, still behind a runtime flag — "
                           "nothing can call it yet",
    "web_api_removed_gated": "Web API removed, and it was still behind a "
                             "closed flag — no page could reach it",
    "killswitch_retired": "Kill-switch flag retired (feature now permanent)",
    "experimental_dropped": "Experimental flag dropped",
    "web_api_signature_change": "Web API signature changed",
    "web_api_overload_removed": "Web API overload removed — the member is "
                                "still there, but one of the argument lists "
                                "it accepted is gone",
    "web_api_overload_added": "Web API gained an overload — a new argument "
                              "list on a member that already existed, taking "
                              "an argument count nothing else took",
    "web_api_overload_shadowed": "Web API gained an overload with an argument "
                                 "count another already had — resolution picks "
                                 "by count first, so an existing call can now "
                                 "reach a different one",
    "ipc_signature_change": "Mojo method signature changed (ABI)",
    "ipc_removed": "Mojo interface/method removed",
    "ipc_ordinal_changed": "Mojo method ordinal changed (ABI) — the other "
                           "process routes this message by that number, so it "
                           "now reaches a different method or none",
    "ipc_shape_changed": "Mojo data shape changed (ABI) — the other process "
                         "reads these bytes as something else",
    "ipc_enum_changed": "Mojo enum members changed — a peer that does not know "
                        "a value rejects the message rather than misreading it",
    "ipc_stability_changed": "Mojo stability promise changed — `[Stable]` "
                             "appeared or went away, which decides whether a "
                             "later reorder breaks a peer",
    "ipc_field_annotated": "Mojo field's default or version annotation changed",
    "pref_renamed": "Preference key renamed (stored values orphaned)",
    "switch_renamed": "Command-line switch renamed",
    "pref_left_scan": "Preference no longer in the file we read — it may have "
                      "been deleted, orphaning stored values, or simply moved "
                      "to one of the ~100 pref files outside the scan",
    "switch_left_scan": "Command-line switch no longer in the files we read — "
                        "deleted, or moved outside the scan",
    "feature_string_renamed": "Finch feature name renamed (field trials and "
                              "--enable-features stop matching)",
    "feature_symbol_renamed": "C++ identifier renamed (code writing "
                              "features::kOldName no longer compiles)",
    "pref_symbol_renamed": "Preference key kept, its C++ constant renamed "
                           "(code writing prefs::kOldName no longer compiles; "
                           "stored values are safe)",
    "switch_symbol_renamed": "Switch kept, its C++ constant renamed (code "
                             "writing switches::kOldName no longer compiles; "
                             "launch scripts are safe)",
    "declaration_moved": "Declaration moved to another file",
    "ui_page_removed": "Settings/WebUI page removed",
    "ui_page_added": "New Settings/WebUI page",
    "ui_page_regated": "Page now shown under a different flag — check whether "
                       "users saw the switch in an earlier milestone",
    "ui_page_moved": "Page URL or parent changed",
    "ui_control_type_changed": "Control type changed (e.g. dropdown became a "
                               "toggle)",
    "ui_control_repointed": "Control now writes a different preference",
    "ui_control_removed": "Control removed from the page",
    "ui_control_added": "New control on the page",
    "ui_gate_changed": "Visibility condition changed",
    "ui_gate_removed": "Visibility condition removed — what it guarded "
                       "is now unconditional, or went with it",
    "ui_gate_added": "New visibility condition",
    "param_default_changed": "Feature parameter default changed",
    "param_removed": "Feature parameter removed — anything still setting it, "
                     "including a server-side Finch config, silently stops "
                     "having an effect",
    "param_rewired": "Feature parameter rewired — its type changed, or it now "
                     "belongs to a different flag",
    "flag_expiring": "Flag scheduled for removal",
    "flag_expiry_moved": "Removal date moved further out — scheduling only, "
                         "no behaviour change",
    "origin_trial_change": "Origin trial wiring changed",
    "web_api_exposure_changed": "Web API exposure changed — an extended "
                                "attribute or the runtime flag gating it "
                                "moved, so who can reach it changed",
    "web_api_shape_changed": "Web API shape changed — an interface's "
                             "inheritance or an enum's member list moved",
    "web_api_status_moved": "Blink flag moved between test and experimental — "
                            "not yet stable, so users see nothing",
    "runtime_flag_rewired": "Blink flag rewired — the base::Feature behind it, "
                            "what it depends on, or its visibility changed",
    "build_gate_changed": "Build condition changed — this declaration may no "
                          "longer be in the binary we ship",
    "ui_control_relabelled": "Control's label changed",
}

# Which bucket a change lands in, decided by the signal that set its severity.
#
# The bucket answers "what kind of thing happened", which is the only question
# this tool can answer on its own: it has one Chromium version and another, and
# no description of who is reading. So the classification is a property of the
# change, and a finding is filed under the same sentence it is ranked by.
#
# A test holds this table to exactly the keys of SIGNAL_SEVERITY, because a
# signal with no bucket would silently fall through to the direction rule and
# be filed by "something was removed" rather than by what the removal was.
SIGNAL_BUCKET: Dict[str, str] = {
    # -- Breaking: something outside the binary stops working, silently.
    "ipc_signature_change": BUCKET_BREAKING,
    "ipc_removed": BUCKET_BREAKING,
    # The data half of the same boundary, and the same bucket for the same
    # reason: a field read as a different type on the far side fails exactly
    # the way a moved method parameter does, and nothing warns either.
    "ipc_shape_changed": BUCKET_BREAKING,
    "ipc_ordinal_changed": BUCKET_BREAKING,
    "ipc_enum_changed": BUCKET_BREAKING,
    # Not breaking: what an older peer sees changes, but every byte on the
    # wire is still read as the thing it is.
    "ipc_field_annotated": BUCKET_BEHAVIOUR,
    "ipc_stability_changed": BUCKET_BEHAVIOUR,
    "web_api_removed": BUCKET_BREAKING,
    "web_api_unshipped": BUCKET_BREAKING,
    "web_api_signature_change": BUCKET_BREAKING,
    "web_api_overload_removed": BUCKET_BREAKING,
    "web_api_overload_added": BUCKET_NEW,
    "web_api_overload_shadowed": BUCKET_BEHAVIOUR,
    "pref_renamed": BUCKET_BREAKING,
    "pref_symbol_renamed": BUCKET_BREAKING,
    "switch_renamed": BUCKET_BREAKING,
    "switch_symbol_renamed": BUCKET_BREAKING,
    "feature_string_renamed": BUCKET_BREAKING,
    "feature_symbol_renamed": BUCKET_BREAKING,
    "param_rewired": BUCKET_BREAKING,
    "param_removed": BUCKET_BREAKING,
    # The control still exists and writes somewhere else, so the value the
    # user already set is stranded -- the same consequence as a renamed key.
    "ui_control_repointed": BUCKET_BREAKING,
    # Deletion or move; the run's own coverage decides which is the likelier
    # reading, and the scoring stage moves these to housekeeping when the run
    # did not read enough of the tree to tell. See score.py.
    "pref_left_scan": BUCKET_BREAKING,
    "switch_left_scan": BUCKET_BREAKING,

    # -- Behaviour: the Windows build behaves differently.
    "enabled_by_default": BUCKET_BEHAVIOUR,
    "disabled_by_default": BUCKET_BEHAVIOUR,
    "default_flip_on": BUCKET_BEHAVIOUR,
    "default_flip_off": BUCKET_BEHAVIOUR,
    "new_feature_on_by_default": BUCKET_BEHAVIOUR,
    "web_api_shipped": BUCKET_BEHAVIOUR,
    "web_api_shape_changed": BUCKET_BEHAVIOUR,
    "web_api_exposure_changed": BUCKET_BEHAVIOUR,
    "param_default_changed": BUCKET_BEHAVIOUR,
    "origin_trial_change": BUCKET_BEHAVIOUR,
    "build_gate_changed": BUCKET_BEHAVIOUR,
    # The one removal whose prior state could not be read, so a behaviour
    # change cannot be ruled out. Its two siblings can be, and are below.
    "feature_deleted": BUCKET_BEHAVIOUR,
    "ui_page_removed": BUCKET_BEHAVIOUR,
    "ui_page_regated": BUCKET_BEHAVIOUR,
    "ui_page_moved": BUCKET_BEHAVIOUR,
    "ui_control_removed": BUCKET_BEHAVIOUR,
    "ui_control_type_changed": BUCKET_BEHAVIOUR,
    "ui_gate_changed": BUCKET_BEHAVIOUR,
    "ui_gate_removed": BUCKET_BEHAVIOUR,

    # -- New surface: something exists that did not, and nothing is on by it.
    "web_api_added": BUCKET_NEW,
    "web_api_added_live": BUCKET_NEW,
    "web_api_added_gated": BUCKET_NEW,
    "web_api_removed_gated": BUCKET_HOUSEKEEPING,
    "ui_page_added": BUCKET_NEW,
    "ui_control_added": BUCKET_NEW,
    "ui_gate_added": BUCKET_NEW,

    # -- Housekeeping: Chromium tidying up after itself, and scheduling.
    #
    # The three retirements belong here and it is the single most consequential
    # row in this table. A retired flag is Chromium deleting a switch it no
    # longer needs *after* the outcome settled -- 90 of them at M148 -> M151,
    # split 45/45 -- and none of them changes behaviour. Filing them as
    # breakage is how half a report becomes false alarms.
    "flag_retired_on": BUCKET_HOUSEKEEPING,
    "flag_retired_off": BUCKET_HOUSEKEEPING,
    "killswitch_retired": BUCKET_HOUSEKEEPING,
    "experimental_dropped": BUCKET_HOUSEKEEPING,
    "declaration_moved": BUCKET_HOUSEKEEPING,
    "flag_expiring": BUCKET_HOUSEKEEPING,
    "flag_expiry_moved": BUCKET_HOUSEKEEPING,
    "web_api_status_moved": BUCKET_HOUSEKEEPING,
    "runtime_flag_rewired": BUCKET_HOUSEKEEPING,
    # The tool reads the loadTimeData key, never the display string -- that
    # lives in a .grd it does not open. So a relabelled control may or may not
    # be visible to anyone, and at severity 20 it does not belong in a bucket
    # people read line by line.
    "ui_control_relabelled": BUCKET_HOUSEKEEPING,
}

# When a change carries no signal, the direction is the whole story and it
# decides the bucket. A removal nothing could characterise is cleanup until
# something says otherwise; the two removals that are *not* -- a feature
# parameter and a preference -- have signals of their own above.
NO_SIGNAL_BUCKET = {
    ADDED: BUCKET_NEW,
    REMOVED: BUCKET_HOUSEKEEPING,
    MODIFIED: BUCKET_BEHAVIOUR,
}


# ---------------------------------------------------------------------------


def meaningful_attrs(fact: Fact) -> dict:
    """The attributes of a fact that a comparison treats as carrying meaning.

    Public because three modules have to answer "is our version the same as
    theirs", and each answering it with its own definition of "same" is how one
    of them ends up quietly weaker than the others -- which is exactly what
    happened to the shadow analysis, comparing only ``default_state`` and so
    reading a Windows-branch override as untouched.
    """
    keys = MEANINGFUL_ATTRS.get(fact.kind)
    if keys is None:
        return dict(fact.attrs)
    return {k: fact.attrs[k] for k in keys if k in fact.attrs}


_meaningful = meaningful_attrs


def _our_state(fact: Fact) -> str:
    ps = fact.attrs.get("platform_state") or {}
    if isinstance(ps, dict) and ps.get(PLATFORM):
        return ps[PLATFORM]
    return fact.attrs.get("default_state", "")


def _our_status(fact: Fact) -> str:
    ps = fact.attrs.get("platform_status") or {}
    if isinstance(ps, dict) and ps.get(PLATFORM):
        return ps[PLATFORM]
    return fact.attrs.get("windows_status", "")


class Gates:
    """What stands between a web API declaration and a page that calls it.

    The three-stage rule is not a rule about flags. It is a rule about gates:
    between "the code exists" and "someone can see it" there is always
    something holding the door, and a flag is only its commonest form. Blink
    spells this one `[RuntimeEnabled=Foo]`, and resolving it needs the status
    of `Foo` -- a gate whose flag already reached stable is an open gate, so
    the attribute alone says nothing.

    Two ways of being gated, and the tool read neither: the attribute on the
    member, and the same attribute on the interface holding it. Measured
    M148 -> M151 on 220 added members, 133 are reachable by a page on arrival
    and 87 are not, and every one of them was reported at the same 30 points
    under the same sentence.
    """

    __slots__ = ("before", "after")

    def __init__(self, old: Snapshot, new: Snapshot) -> None:
        self.before = _side_gates(old)
        self.after = _side_gates(new)


def _side_gates(snapshot: Snapshot) -> Tuple[Dict[str, str], Dict[str, str]]:
    """One side's runtime-flag statuses, and which interfaces are gated."""
    status: Dict[str, str] = {}
    interfaces: Dict[str, str] = {}
    for fact in snapshot.facts:
        if fact.kind == KIND_BLINK_RUNTIME:
            status[fact.key] = _our_status(fact)
        elif fact.kind == KIND_IDL_INTERFACE:
            gate = (fact.attrs.get("ext") or {}).get("RuntimeEnabled", "")
            if gate:
                interfaces[fact.key] = gate
    return status, interfaces


def _gate_names(fact: Fact, interfaces: Dict[str, str]) -> List[str]:
    if fact.kind == KIND_IDL_INTERFACE:
        gate = (fact.attrs.get("ext") or {}).get("RuntimeEnabled", "")
        return [gate] if gate else []
    return [n for n in (fact.attrs.get("runtime_enabled", ""),
                        interfaces.get(fact.attrs.get("interface", ""), ""))
            if n]


def _reachable(fact: Optional[Fact],
               side: Tuple[Dict[str, str], Dict[str, str]]) -> Optional[bool]:
    """Can a page call this today? None when the gate is outside the read.

    Gates are ANDed, the way build conditions are: a member behind two flags
    needs both open. None rather than a guess when the flag is not in the
    snapshot, for the same reason a non-platform BUILDFLAG stays
    `conditional` -- a `default` run reads a third of the flags.
    """
    if fact is None:
        return None
    status, interfaces = side
    names = _gate_names(fact, interfaces)
    if not names:
        return True
    for name in names:
        state = status.get(name)
        if state is None:
            return None
        if state != "stable":
            return False
    return True


def diff_snapshots(old: Snapshot, new: Snapshot, platform: str = PLATFORM,
                   target_milestone: Optional[int] = None) -> List[Change]:
    """Produce the semantic change list between two snapshots.

    Refuses to compare snapshots built from different target sets: one side
    would be missing whole categories of fact, so every fact only the wider
    side collected reads as an addition.  Failing loudly beats emitting a
    report whose numbers look reasonable and are not.
    """
    old_set = ((old.meta or {}).get("target_set"),
               tuple((old.meta or {}).get("partitions") or ()),
               bool((old.meta or {}).get("complete")))
    new_set = ((new.meta or {}).get("target_set"),
               tuple((new.meta or {}).get("partitions") or ()),
               bool((new.meta or {}).get("complete")))
    if old_set != new_set:
        raise ValueError(
            f"cannot diff snapshots built from different target sets "
            f"({old.ref}={old_set!r}, {new.ref}={new_set!r}); rebuild one with "
            f"--target-set {new_set or old_set!r} or pass --refresh"
        )

    _refuse_lopsided(old, new)

    old_index = old.index()
    new_index = new.index()
    gates = Gates(old, new)

    changes: List[Change] = []

    for uid, new_fact in new_index.items():
        old_fact = old_index.get(uid)
        if old_fact is None:
            changes.append(_make_change(ADDED, None, new_fact, platform,
                                        target_milestone, gates=gates))
            continue
        before = _meaningful(old_fact)
        after = _meaningful(new_fact)
        deltas: Dict[str, List] = {}
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                deltas[key] = [before.get(key), after.get(key)]
        if old_fact.path and new_fact.path and old_fact.path != new_fact.path:
            deltas["path"] = [old_fact.path, new_fact.path]
        if not deltas:
            continue
        changes.append(_make_change(MODIFIED, old_fact, new_fact, platform,
                                    target_milestone, deltas, gates))

    for uid, old_fact in old_index.items():
        if uid not in new_index:
            changes.append(_make_change(REMOVED, old_fact, None, platform,
                                        target_milestone, gates=gates))

    # Pairing a removal with an addition by C++ variable detects a rename.
    changes = _detect_renames(changes)
    # Same shape of problem as a rename, on a different identity: the part of a
    # control's key that moved is the preference it writes.
    changes = _detect_repointed_controls(changes)
    changes.sort(key=lambda c: (-c.severity, c.kind, c.key))
    return changes


# How far apart two sides may be before the comparison stops meaning anything.
# Two real Chromium versions eight milestones apart differ by about 3%
# (M143 24,113 facts against M151 24,959), so half is far outside anything
# legitimate.
LOPSIDED_RATIO = 0.5

# ...and below which the ratio means nothing. A handful of facts on each side is
# a unit test's fixture, where one against three is normal rather than alarming.
# The smallest real run is `--target-set minimal` at about 1,700 facts and the
# smallest partition about 2,700, so this floor sits far under anything a real
# comparison produces and far over anything a fixture does.
LOPSIDED_MIN_FACTS = 500


def _refuse_lopsided(old: Snapshot, new: Snapshot) -> None:
    """Refuse when one side read a fraction of what the other did.

    The target-set guard above is one derivation short of its own reasoning.
    It compares the *label* a snapshot was built under, which catches
    `--target-set minimal` against `default` and nothing else; two sides both
    labelled "default" pass it even when one of them is a truncated tree.

    That is not hypothetical, and `--local-src` / `--to-src` is how it happens.
    Pointed at a partial checkout, one side of a real run held 1,647 facts
    against the other's 24,959 -- 6.6% -- and the tool said nothing at all. It
    printed "scope: ok" twice, because every fact really did come from a file
    the target set asked for, and then reported 23,318 removals. None of them
    had happened.

    Coverage cannot catch it either: that number is measured against whatever
    tree it is pointed at, so the truncated side scored 8 of 13 candidate files
    -- 62%, which reads as healthy.

    The only thing that sees it is the two sides side by side, which is what
    this does. Failing loudly beats emitting a report whose numbers look
    reasonable and are not.
    """
    old_n, new_n = len(old.facts), len(new.facts)
    if max(old_n, new_n) < LOPSIDED_MIN_FACTS:
        return
    if not old_n or not new_n:
        smaller, larger = (old, new) if old_n <= new_n else (new, old)
        raise ValueError(
            f"{smaller.ref} produced no facts at all while {larger.ref} "
            f"produced {max(old_n, new_n)}; the ref or the checkout it was "
            f"read from is wrong. Nothing can be compared against an empty "
            f"side -- every fact on the other one would read as a removal."
        )
    if min(old_n, new_n) >= LOPSIDED_RATIO * max(old_n, new_n):
        return
    smaller, larger = (old, new) if old_n < new_n else (new, old)
    small_n, large_n = min(old_n, new_n), max(old_n, new_n)
    raise ValueError(
        f"cannot diff: {smaller.ref} holds {small_n:,} facts against "
        f"{larger.ref}'s {large_n:,} ({100 * small_n // large_n}%). Two "
        f"versions of Chromium differ by a few percent, so a gap this size is "
        f"a truncated tree rather than a change -- check the --local-src / "
        f"--from-src / --to-src path points at a full Chromium src/ (the "
        f"directory holding content/ and third_party/), and re-run that side "
        f"with --refresh. Compared as-is, every fact only {larger.ref} has "
        f"would be reported as something the other side removed."
    )


def _locations(*facts) -> List[str]:
    """"path:line" for each side, deduplicated, in the order given."""
    out: List[str] = []
    for fact in facts:
        if fact is None or not fact.path:
            continue
        where = f"{fact.path}:{fact.line}" if fact.line else fact.path
        if where not in out:
            out.append(where)
    return out


def _merge_locations(*changes) -> List[str]:
    out: List[str] = []
    for change in changes:
        for where in change.locations:
            if where not in out:
                out.append(where)
    return out


def _make_change(change_type: str, old_fact: Optional[Fact],
                 new_fact: Optional[Fact], platform: str,
                 target_milestone: Optional[int],
                 deltas: Optional[Dict[str, List]] = None,
                 gates: Optional[Gates] = None) -> Change:
    fact = new_fact or old_fact
    assert fact is not None
    paths = sorted({p for p in ((old_fact.path if old_fact else ""),
                                (new_fact.path if new_fact else "")) if p})
    change = Change(
        change_type=change_type,
        kind=fact.kind,
        key=fact.key,
        name=fact.name,
        before=old_fact.attrs if old_fact else None,
        after=new_fact.attrs if new_fact else None,
        deltas=deltas or {},
        paths=paths,
        locations=_locations(old_fact, new_fact),
    )
    change.signals = _signals_for(change, old_fact, new_fact, platform,
                                  target_milestone, gates)
    change.severity = _severity_for(change)
    return change


def leading_signal(change: Change) -> str:
    """The signal that set this change's severity floor, or "" if it has none.

    The reports group findings by it and print its label as the headline, so it
    has to be the same pick the severity used -- a report that files a row under
    "Flag scheduled for removal" while its score came from "Shipped, then flag
    retired" is describing a different change from the one it ranked. Ties break
    on the name so the choice does not depend on signal order.
    """
    if not change.signals:
        return ""
    return max(change.signals, key=lambda s: (SIGNAL_SEVERITY.get(s, 0), s))


def _severity_for(change: Change) -> int:
    """What this change costs, from the most precise thing that can be said.

    The signal is a statement about what happened; ``BASE_SEVERITY`` is a guess
    from the kind and the direction. So the signal decides, and the guess is
    used only when there is no signal at all.

    It used to be ``max(base, floor)``, which sounds cautious and is not: the
    guess overrode the statement in exactly the cases where the statement was
    lower, which is where the guess was wrong. A Mojo method whose mojom
    attributes moved and one whose signature moved both scored 75, because
    ``(mojo_method, modified)`` is 75 and only the second is an ABI break. A
    chrome://flags entry whose removal date slipped scored 15 while its own
    signal says 10, and the code that set it said so in a comment: "below the
    kind's own base severity, so labelling these changes no ranking".

    Measured against two real pairs, the prior overrode the signal on 267 of
    2,800 findings at M148 -> M151 and 345 of 6,787 at M143 -> M151, every one
    of them upwards. The largest group is the smallest change the tool
    reports -- a chrome://flags removal date slipping, 245 and 256 of them --
    and the most wrong is the four Mojo methods whose mojom attributes moved
    and which were ranked as ABI breaks at 75.
    """
    lead = leading_signal(change)
    if lead:
        return SIGNAL_SEVERITY.get(lead, 0)
    return BASE_SEVERITY.get((change.kind, change.change_type), 20)


def bucket_of(change: Change) -> str:
    """Which bucket a change belongs to, from the signal that set its severity.

    Public because the scoring stage may move one class of finding out of it --
    a disappearance the run did not read enough of the tree to confirm -- and
    it has to start from the same answer both renderers group by.
    """
    lead = leading_signal(change)
    if lead:
        bucket = SIGNAL_BUCKET.get(lead)
        if bucket:
            return bucket
    return NO_SIGNAL_BUCKET.get(change.change_type, BUCKET_HOUSEKEEPING)


# Signals whose fix is not where the declaration is. Everything else is owned
# by the surface it was declared on, which `KIND_OWNERS` decides.
#
# The test is where the edit has to happen, not what broke. A renamed C++
# constant stops the build and is fixed in the file next to it; a renamed Finch
# string compiles perfectly and is fixed in a server-side config nobody can
# see from this repository. Those are the same event to a diff and two
# different jobs, and only the second one can sit unnoticed for a milestone.
SIGNAL_OWNERS = {
    "feature_string_renamed": OWNER_CONFIG,
    "switch_renamed": OWNER_CONFIG,
    "param_removed": OWNER_CONFIG,
    "param_rewired": OWNER_CONFIG,
    # A retired flag changes nothing in the binary and silently kills any
    # override that was setting it from outside -- which is the only reason
    # anyone needs to know, and it is not a C++ job.
    "flag_retired_on": OWNER_CONFIG,
    "flag_retired_off": OWNER_CONFIG,
    "killswitch_retired": OWNER_CONFIG,
    # The one thing in Housekeeping about work that has not happened yet.
    "flag_expiring": OWNER_CONFIG,
    # And its quieter half: a removal date moving is scheduling news for
    # whoever depends on being able to set the flag, which is never the person
    # who owns the file it is declared in.
    "flag_expiry_moved": OWNER_CONFIG,
}


def owner_of(change: Change) -> str:
    """Whose desk this lands on.

    Same shape as `bucket_of`, and for the same reason: the signal is the
    precise statement and the kind is the fallback, so a row is routed by what
    happened rather than by which file it was found in.
    """
    lead = leading_signal(change)
    if lead in SIGNAL_OWNERS:
        return SIGNAL_OWNERS[lead]
    return KIND_OWNERS.get(change.kind, OWNER_NATIVE)


def _arity_range(signature: str):
    """The argument counts this overload can actually be called with.

    Not the declared parameter count. Web IDL builds an *effective* overload
    set: an `optional` argument contributes one entry per count from the
    required number upward, and a variadic one contributes every count from
    its fixed number up. So `f(optional long a)` answers a call with none and
    a call with one, and the declared number 1 describes neither end.

    Returns `(minimum, maximum)`, with `None` for a variadic maximum.
    """
    open_at = signature.find("(")
    if open_at == -1:
        return (0, 0)
    inner = signature[open_at + 1:signature.rfind(")")].strip()
    if not inner:
        return (0, 0)
    parts, depth, current = [], 0, ""
    for ch in inner:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    required = 0
    variadic = False
    for part in parts:
        text = part.strip()
        if "..." in text:
            variadic = True
            continue
        if not text.startswith("optional "):
            required += 1
    return (required, None if variadic else len(parts))


def _overload_signals(before, after) -> List[str]:
    """What changing an overload set does, by direction and by reachability.

    Losing an entry is a callable shape disappearing: a site passing that
    argument list stops matching.

    Gaining one is not automatically harmless, and two earlier versions of
    this said it was. Resolution counts arguments first, so a new entry
    answering a count something already answered can take a call from it --
    `Navigator.install(InstallParams)` beside `install(USVString)`, both at
    one argument. And a call with *more* arguments than any overload declares
    is served by the longest one with the extras dropped, so adding a longer
    overload also captures calls that were landing on the old longest.

    Safe therefore means: every count this entry serves was unreachable
    before, and it does not raise the ceiling that over-long calls fall back
    to.
    """
    before, after = set(before or ()), set(after or ())
    out: List[str] = []
    if before - after:
        out.append("web_api_overload_removed")
    added = after - before
    if not added:
        return out

    served = set()
    ceiling = 0
    for sig in before:
        low, high = _arity_range(sig)
        if high is None:
            ceiling = None
        elif ceiling is not None:
            ceiling = max(ceiling, high)
        served.update(range(low, (high if high is not None else low) + 1))

    shadows = False
    for sig in added:
        low, high = _arity_range(sig)
        top = high if high is not None else low
        if served & set(range(low, top + 1)):
            shadows = True
        elif ceiling is not None and (high is None or high > ceiling):
            # An over-long call used to be clamped onto the previous longest
            # overload. It now has somewhere exact to land.
            shadows = True
    out.append("web_api_overload_shadowed" if shadows
               else "web_api_overload_added")
    return out


def _signals_for(change: Change, old_fact: Optional[Fact],
                 new_fact: Optional[Fact], platform: str,
                 target_milestone: Optional[int],
                 gates: Optional[Gates] = None) -> List[str]:
    signals: List[str] = []
    kind = change.kind

    if kind == KIND_BASE_FEATURE:
        signals += _base_feature_signals(change, old_fact, new_fact, platform)
    elif kind == KIND_BLINK_RUNTIME:
        signals += _blink_signals(change, old_fact, new_fact)
    elif kind in (KIND_IDL_MEMBER, KIND_IDL_INTERFACE):
        # Both directions ask the gate first. An addition a page cannot reach
        # is stage A of the three-stage rule, and a removal of something no
        # page could reach is stage C -- the same distinction the flag signals
        # have always made, applied to the surface that carries 14,549 of the
        # tree's facts. When the gate names a flag this run did not read, the
        # undecided signal keeps its old name and its old severity.
        if change.change_type == REMOVED:
            was = _reachable(old_fact, gates.before) if gates else True
            signals.append("web_api_removed" if was is not False
                           else "web_api_removed_gated")
        elif change.change_type == ADDED:
            now = _reachable(new_fact, gates.after) if gates else None
            signals.append("web_api_added" if now is None else
                           "web_api_added_live" if now else "web_api_added_gated")
        else:
            # `member_type` is what a member *is* -- an attribute becoming an
            # operation is a different call at every call site -- so it belongs
            # with the signature rather than in a category of its own.
            # When the overload set moved, the surviving declaration's own
            # signature moving with it is a fact about which copy
            # deduplication kept, not independent evidence -- the overload
            # signals below say the same event more precisely. Reporting both
            # put a 50-point "signature changed" above a 25-point overload
            # addition for a member that gained one and lost nothing.
            if ("signatures" not in change.deltas
                    and any(a in change.deltas
                            for a in ("signature", "idl_kind", "member_type"))):
                signals.append("web_api_signature_change")
            # The overload set, which the member's own signature cannot show:
            # deduplication keeps one declaration, so a sibling overload
            # appearing or disappearing moved nothing that branch could see.
            #
            # Not an `elif`. Whether the surviving declaration also changed is
            # a fact about which copy deduplication kept, and hanging the
            # signal on it made one event score 60 or 50 depending on
            # declaration order. Both statements are emitted and
            # `leading_signal` picks; the answer no longer depends on the file.
            if "signatures" in change.deltas:
                # A member going from one declaration to two has no
                # `signatures` on the old side -- the list is only written
                # when there is more than one -- so the old set has to come
                # from its single `signature`, or every first overload reads
                # as reaching an argument count nothing had.
                was, now = change.deltas["signatures"]
                if not was and old_fact is not None:
                    was = [old_fact.attrs.get("signature", "")]
                if not now and new_fact is not None:
                    now = [new_fact.attrs.get("signature", "")]
                signals += _overload_signals(was, now)
            # One overload's gate moving while the argument lists stay put.
            # Deduplication keeps one declaration, so unless the copy it kept
            # was the one that moved, this said nothing. It is the same event
            # `web_api_exposure_changed` names for a member with a single
            # declaration, so it carries that name rather than a new one.
            if ("overload_traits" in change.deltas
                    and "web_api_exposure_changed" not in signals):
                signals.append("web_api_exposure_changed")
            # `inherits` moves the prototype chain, `values` adds or drops an
            # enum member -- both change what a site can write, and both were
            # compared without ever producing a row anyone could read.
            if "inherits" in change.deltas or "values" in change.deltas:
                signals.append("web_api_shape_changed")
            # Extended attributes and [RuntimeEnabled=] decide which contexts
            # the member exists in and which flag turns it on.
            if "ext" in change.deltas or "runtime_enabled" in change.deltas:
                signals.append("web_api_exposure_changed")
    elif kind in (KIND_MOJO_STRUCT, KIND_MOJO_FIELD, KIND_MOJO_ENUM):
        if change.change_type == REMOVED:
            signals.append("ipc_removed")
        elif change.change_type == MODIFIED:
            if "values" in change.deltas:
                signals.append("ipc_enum_changed")
            # Type, ordinal and struct-versus-union are the wire format; a
            # default or a `[MinVersion]` is what an older peer sees.
            if any(a in change.deltas
                   for a in ("type", "ordinal", "position", "mojo_kind")):
                signals.append("ipc_shape_changed")
            elif any(a in change.deltas
                     for a in ("default", "attrs", "min_version", "stable")):
                signals.append("ipc_field_annotated")
    elif kind in (KIND_MOJO_METHOD, KIND_MOJO_INTERFACE):
        if change.change_type == REMOVED:
            signals.append("ipc_removed")
        elif change.change_type == MODIFIED:
            if ("signature" in change.deltas or "params" in change.deltas
                    or "response" in change.deltas):
                signals.append("ipc_signature_change")
            elif "ordinal" in change.deltas or "position" in change.deltas:
                # `position` is only recorded inside `[Stable]`, where mojom
                # assigns the wire id from it and promises it will not move.
                signals.append("ipc_ordinal_changed")
            elif "attrs" in change.deltas:
                # The mojom attributes on a method, which is where the build
                # condition lives: `[EnableIfNot=is_android|is_ios]` appearing
                # on `LocalMainFrameHost.Maximize` decides whether the method
                # is in our binary at all. Compared since the kind was added,
                # labelled by nothing -- four such rows in M143 -> M148.
                signals.append("build_gate_changed")
    elif kind == KIND_FEATURE_PARAM:
        if change.change_type == REMOVED:
            signals.append("param_removed")
        if "default" in change.deltas:
            signals.append("param_default_changed")
        if "var" in change.deltas:
            signals.append("feature_symbol_renamed")
        if "type" in change.deltas or "feature" in change.deltas:
            signals.append("param_rewired")
    elif kind == KIND_WEBUI_ROUTE:
        signals += _webui_route_signals(change)
    elif kind == KIND_WEBUI_CONTROL:
        signals += _webui_control_signals(change)
    elif kind == KIND_WEBUI_GATE:
        if change.change_type == REMOVED:
            # The condition itself is gone: whatever it guarded is now
            # unconditional, or the thing it guarded went with it.
            signals.append("ui_gate_removed")
        elif change.change_type == ADDED:
            signals.append("ui_gate_added")
        elif ("expression" in change.deltas or "features" in change.deltas
              or "enabled_checks" in change.deltas):
            signals.append("ui_gate_changed")
    elif kind in (KIND_PREF, KIND_SWITCH):
        if change.change_type == REMOVED:
            # Rename detection runs as a post-pass and replaces this change
            # outright when it can pair the two sides by C++ variable, so
            # anything still here is a disappearance we could not explain.
            signals.append("pref_left_scan" if kind == KIND_PREF
                           else "switch_left_scan")
        elif "platform_state" in change.deltas:
            # The `#if` chain around the declaration moved it into or out of a
            # Windows build. Only the resolved verdict is compared, so Chromium
            # tidying a guard that never excluded us is not a row.
            signals.append("build_gate_changed")
        elif "var" in change.deltas:
            # The mirror of pref_renamed: there the string moved and the
            # identifier held, here the identifier moved and the string held.
            # `var` has been compared since the identifier audit, but only
            # base::Feature ever got a label out of it, so these arrived with a
            # severity and a blank reason. Two real ones at M148 -> M151:
            # kPreinstalledApps -> kPreinstalledExtensions on `default_apps`.
            signals.append("pref_symbol_renamed" if kind == KIND_PREF
                           else "switch_symbol_renamed")
    elif kind == KIND_FLAG_ENTRY:
        if change.change_type in (ADDED, MODIFIED) and new_fact is not None:
            expiry = new_fact.attrs.get("expiry_milestone")
            if (isinstance(expiry, int) and target_milestone
                    and 0 < expiry <= target_milestone + 2):
                signals.append("flag_expiring")
        if change.change_type == MODIFIED and "expiry_milestone" in change.deltas \
                and "flag_expiring" not in signals:
            signals.append("flag_expiry_moved")

    if "path" in change.deltas:
        signals.append("declaration_moved")

    # A declaration entering or leaving the Windows build, on any kind that
    # can say so. `score._not_in_build` has always known that this is the
    # change rather than a reason to discount one -- "a declaration entering
    # or leaving our binary is the change" -- but `platform_state` was
    # compared on three of the sixteen kinds, so a Mojo method or a settings
    # control becoming Android-only produced no row at all. The same two-door
    # mistake as the Mojo ordinal: recorded on the fact, invisible to the
    # diff.
    if "platform_state" in change.deltas and not signals:
        signals.append("build_gate_changed")

    # A declaration gaining or losing `[Stable]`. Mojo promises wire
    # compatibility for a stable one and nothing for the rest, so this is the
    # promise itself moving -- on any of the five Mojo kinds, and above the
    # annotation signal that already covers a field's own attributes.
    if "stable" in change.deltas and "ipc_field_annotated" not in signals:
        signals.append("ipc_stability_changed")

    # The guard moved between the declaration and the container around it,
    # without the Windows verdict moving. Nothing changes for this build and
    # the next edit to either one now lands differently.
    if "inherited_conditions" in change.deltas and not signals:
        signals.append("build_gate_changed")

    return signals


def _base_feature_signals(change: Change, old_fact: Optional[Fact],
                          new_fact: Optional[Fact],
                          platform: str = PLATFORM) -> List[str]:
    signals: List[str] = []
    if change.change_type == REMOVED:
        # A disappearing base::Feature is usually cleanup, not a lost feature --
        # the same lifecycle already handled for Blink runtime flags. Chromium
        # deletes the flag once the outcome is settled, so the state it held
        # just before deletion says which outcome that was.
        #
        # Measured on M148 -> M151 for Windows: 90 flags removed, split exactly
        # 45/45 between the two cases. Labelling all 90 "feature deleted" makes
        # half the list false alarms.
        #
        # Neither case changes behaviour on its own: the feature simply becomes
        # unconditional. What stops working is anything that was setting the
        # flag from outside the binary -- a Finch config, an --enable-features
        # command line -- which is why the label says so and the bucket does
        # not: nothing a user can see moved.
        prior = _our_state(old_fact) if old_fact else ""
        if old_fact is not None:
            states = old_fact.attrs.get("platform_state") or {}
            if isinstance(states, dict) and states.get(platform):
                prior = states[platform]
        if prior == "enabled":
            return ["flag_retired_on"]
        if prior == "disabled":
            return ["flag_retired_off"]
        return ["feature_deleted"]
    if change.change_type == ADDED and new_fact is not None:
        if _our_state(new_fact) == "enabled":
            signals.append("new_feature_on_by_default")
        return signals
    if old_fact is None or new_fact is None:
        return signals

    old_state = _our_state(old_fact)
    new_state = _our_state(new_fact)
    if old_state != new_state:
        if new_state == "enabled":
            signals.append("enabled_by_default")
        elif new_state == "disabled":
            signals.append("disabled_by_default")
        else:
            # Windows moved to or from "conditional" / "not_compiled": the
            # feature did not flip, the guard deciding whether it is in our
            # build did. Without this the state moved, the row was emitted and
            # nothing said why -- two of them in M143 -> M148.
            signals.append("build_gate_changed")

    # The `#if` chain around the declaration moved. This is compared -- it is
    # the whole evidence for a feature moving into or out of a build without
    # its value changing -- and it was the one compared
    # attribute of the tool's highest-value kind that never produced a label:
    # 55 rows in M143 -> M148 arrived with a severity and a blank reason.
    # Switches, preferences and WebUI controls have said `build_gate_changed`
    # for exactly this since the guards audit; base::Feature was the omission.
    if ("conditions" in change.deltas
            and "build_gate_changed" not in signals):
        signals.append("build_gate_changed")

    if old_fact.attrs.get("var") != new_fact.attrs.get("var"):
        signals.append("feature_symbol_renamed")

    old_default = old_fact.attrs.get("default_state")
    new_default = new_fact.attrs.get("default_state")
    if old_default != new_default:
        if new_default == "enabled":
            signals.append("default_flip_on")
        elif new_default == "disabled":
            signals.append("default_flip_off")
    return signals


def _webui_route_signals(change: Change) -> List[str]:
    """A page vanishing from the route table is usually a migration.

    Chromium replaces a page by declaring both versions at once, each behind
    its own flag, then deleting the old one once the new flag has shipped. So
    a removal here is only alarming if nothing else took its place, and the
    guard is what tells them apart -- see `guards` on the fact.
    """
    if change.change_type == REMOVED:
        return ["ui_page_removed"]
    if change.change_type == ADDED:
        return ["ui_page_added"]
    signals: List[str] = []
    if "guards" in change.deltas:
        # The condition deciding whether users see this page moved. The
        # user-visible switch happened whenever that flag flipped, which is
        # usually earlier than either version being compared.
        signals.append("ui_page_regated")
    if "route" in change.deltas or "parent" in change.deltas:
        signals.append("ui_page_moved")
    return signals


def _webui_control_signals(change: Change) -> List[str]:
    if change.change_type == REMOVED:
        return ["ui_control_removed"]
    if change.change_type == ADDED:
        return ["ui_control_added"]
    signals: List[str] = []
    if "control" in change.deltas:
        signals.append("ui_control_type_changed")
    if "pref" in change.deltas:
        # The control still exists but now writes somewhere else: the old
        # preference is orphaned and the new one starts from its default.
        signals.append("ui_control_repointed")
    if "build_conditions" in change.deltas:
        # The GRIT `<if expr>` around it moved, which decides whether the
        # control is in this platform's binary at all.
        signals.append("build_gate_changed")
    if "label" in change.deltas:
        signals.append("ui_control_relabelled")
    return signals


def _blink_signals(change: Change, old_fact: Optional[Fact],
                   new_fact: Optional[Fact]) -> List[str]:
    signals: List[str] = []
    if change.change_type == REMOVED:
        # A disappearing runtime flag is almost never a disappearing API.
        # Blink deletes the flag a few milestones *after* the feature ships,
        # so on M139->M143 170 of 202 removals were previously `stable`.
        # Scoring those as API removals would put 170 false alarms at the top
        # of the report.  What actually changed is that the kill-switch is
        # gone: the behaviour is now permanent and unconditional, which only
        # matters to anything that was overriding the flag.  Real API removals
        # are detected from the IDL diff instead.
        old_status = _our_status(old_fact) if old_fact else ""
        if old_status == "stable":
            return ["killswitch_retired"]
        return ["experimental_dropped"]
    if change.change_type == ADDED and new_fact is not None:
        if _our_status(new_fact) == "stable":
            signals.append("web_api_shipped")
        else:
            signals.append("web_api_added")
        return signals
    if old_fact is None or new_fact is None:
        return signals

    old_rank = status_rank(_our_status(old_fact))
    new_rank = status_rank(_our_status(new_fact))
    if new_rank > old_rank and _our_status(new_fact) == "stable":
        signals.append("web_api_shipped")
    elif new_rank < old_rank and _our_status(old_fact) == "stable":
        signals.append("web_api_unshipped")
    elif old_rank != new_rank:
        # A move that neither reaches nor leaves stable: test -> experimental,
        # or a flag appearing with no status at all. Users see nothing either
        # way, which is why it scores low -- but it was compared and produced
        # no row, so the reader could not tell that from an unexplained one.
        signals.append("web_api_status_moved")

    if any(a in change.deltas for a in ("origin_trial_feature_name",
                                        "origin_trial_allows_third_party",
                                        "origin_trial_os", "origin_trial_type",
                                        "origin_trial_allows_insecure")):
        signals.append("origin_trial_change")
    # What turns this flag on from inside the binary, and what it drags with
    # it. `base_feature` going to "none" means the C++ feature that used to
    # control it is gone.
    #
    # The last three are the ones that decide who can reach the flag from
    # outside the renderer -- internals, and the browser process reading or
    # writing it. They were added to the compared set with the note that they
    # "decide who can turn a feature on from outside the binary" and then left
    # out of every signal, so a move produced a row nothing explained.
    if any(a in change.deltas for a in ("base_feature", "base_feature_status",
                                        "depends_on", "implied_by", "public",
                                        "copied_from_base_feature_if",
                                        "settable_from_internals",
                                        "browser_process_read_access",
                                        "browser_process_read_write_access",
                                        "is_protected_feature")):
        signals.append("runtime_flag_rewired")
    # The declared status moved without our platform's value moving -- a flag
    # going from a single `status: "stable"` to a per-platform table that still
    # says stable for Windows. Nothing changes for our users, but the row
    # exists and had nothing to say for itself.
    if "status" in change.deltas and not signals:
        signals.append("runtime_flag_rewired")

    return signals


# ---------------------------------------------------------------------------
# Rename detection
# ---------------------------------------------------------------------------


RENAME_SIGNALS = {
    KIND_PREF: "pref_renamed",
    KIND_SWITCH: "switch_renamed",
    KIND_BASE_FEATURE: "feature_string_renamed",
}


def _detect_repointed_controls(changes: List[Change]) -> List[Change]:
    """Pair a removed and an added control that are the same control.

    A control's identity contains the preference it drives, because the
    preference alone is not unique -- a radio group and each of its buttons
    bind the same one. That is right for identity and wrong for this: when a
    control starts writing a *different* preference, its identity changes with
    it, so the change arrives as an unrelated removal plus addition and the
    `ui_control_repointed` signal can never fire.

    It is not a hypothetical gap. Measured M130 -> M151, 21 controls changed
    the preference they write while keeping their page and element id, and
    every one of them was reported as two unconnected rows.

    The consequence is the same one a renamed preference has: the old key stops
    being written, so a value the user already set is stranded, while the new
    key starts from its default. Pairing on page plus element id -- the parts
    of identity that did *not* move -- recovers it.
    """
    def anchor(attrs: Optional[dict]) -> Optional[tuple]:
        a = attrs or {}
        ident = a.get("element_id") or a.get("label")
        if not ident:
            return None
        return (a.get("surface", ""), a.get("page", ""), ident)

    by_anchor: Dict[tuple, Dict[str, List[Change]]] = {}
    for change in changes:
        if change.kind != KIND_WEBUI_CONTROL:
            continue
        if change.change_type not in (ADDED, REMOVED):
            continue
        key = anchor(change.after if change.change_type == ADDED else change.before)
        if key:
            by_anchor.setdefault(key, {}).setdefault(change.change_type, []).append(change)

    merged: List[Change] = []
    dropped = set()
    for key, group in by_anchor.items():
        added, removed = group.get(ADDED, []), group.get(REMOVED, [])
        if len(added) != 1 or len(removed) != 1:
            continue
        a, r = added[0], removed[0]
        before_pref = (r.before or {}).get("pref", "")
        after_pref = (a.after or {}).get("pref", "")
        if before_pref == after_pref:
            continue  # moved for some other reason; not a repoint
        deltas: Dict[str, List] = {"pref": [before_pref, after_pref]}
        for attr in ("control", "label"):
            old, new = (r.before or {}).get(attr), (a.after or {}).get(attr)
            if old != new:
                deltas[attr] = [old, new]
        signals = ["ui_control_repointed"]
        if "control" in deltas:
            signals.append("ui_control_type_changed")
        repoint = Change(
            change_type=MODIFIED, kind=KIND_WEBUI_CONTROL, key=r.key,
            name=f"{r.name} -> {a.name}",
            before=r.before, after=a.after, deltas=deltas,
            paths=sorted(set(r.paths) | set(a.paths)),
            locations=_merge_locations(r, a), signals=signals,
        )
        repoint.severity = max(SIGNAL_SEVERITY[x] for x in signals)
        merged.append(repoint)
        dropped.add(id(a))
        dropped.add(id(r))

    return [c for c in changes if id(c) not in dropped] + merged


def _detect_renames(changes: List[Change]) -> List[Change]:
    """Pair removed/added facts that share a C++ variable name.

    Identity for these kinds is a *string*, while the C++ variable is stable.
    So a rename arrives as an unrelated removal plus addition, and the real
    consequence hides between them.

    Three cases, all silent failures:

    * a pref key moves and every existing profile's stored value is orphaned;
    * a switch is renamed and launch scripts stop taking effect;
    * a ``base::Feature`` string changes and Finch configs stop matching.

    The last one is not hypothetical.  M139 declared
    ``BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...)``.  M143
    uses the two-argument macro, which derives the string from the variable --
    turning the feature name into ``"FedCmIdPRegistration"``.  Nobody edited a
    name; the macro migration renamed it.  Any server-side field trial or
    ``--enable-features`` flag keyed on the old spelling now silently does
    nothing, and no compiler warns.
    """
    by_kind: Dict[str, Dict[str, List[Change]]] = {}
    for change in changes:
        if change.kind not in RENAME_SIGNALS:
            continue
        if change.change_type not in (ADDED, REMOVED):
            continue
        attrs = change.after if change.change_type == ADDED else change.before
        var = (attrs or {}).get("var")
        if not var:
            continue
        by_kind.setdefault(change.kind, {}).setdefault(var, []).append(change)

    merged: List[Change] = []
    dropped = set()
    for kind, vars_map in by_kind.items():
        for var, group in vars_map.items():
            added = [c for c in group if c.change_type == ADDED]
            removed = [c for c in group if c.change_type == REMOVED]
            if len(added) != 1 or len(removed) != 1:
                continue
            a, r = added[0], removed[0]
            signal = RENAME_SIGNALS[kind]
            rename = Change(
                change_type=MODIFIED,
                kind=kind,
                key=r.key,
                name=f"{r.key} -> {a.key}",
                before=r.before,
                after=a.after,
                deltas={"value": [r.key, a.key]},
                paths=sorted(set(r.paths) | set(a.paths)),
                locations=_merge_locations(r, a),
                signals=[signal],
            )
            rename.severity = SIGNAL_SEVERITY[signal]
            merged.append(rename)
            dropped.add(id(a))
            dropped.add(id(r))

    return [c for c in changes if id(c) not in dropped] + merged


def summarize(changes: List[Change]) -> Dict[str, Dict[str, int]]:
    """Counts by kind and by change type, for the report header."""
    by_kind: Dict[str, Dict[str, int]] = {}
    for change in changes:
        bucket = by_kind.setdefault(change.kind, {ADDED: 0, REMOVED: 0, MODIFIED: 0})
        bucket[change.change_type] = bucket.get(change.change_type, 0) + 1
    return dict(sorted(by_kind.items()))
