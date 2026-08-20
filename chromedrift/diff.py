"""Semantic diff between two snapshots.

The whole point of this stage is to answer "what actually changed" rather than
"what text differs".  Two rules do most of that work:

1. **Attribute whitelists.**  Only attributes with downstream meaning are
   compared.  Between M139 and M143 every ``BASE_FEATURE`` in the tree changed
   its declaration syntax; comparing a ``declared_form`` attribute would emit
   thousands of modifications that mean nothing to anyone.

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
    ADDED,
    KIND_BASE_FEATURE,
    KIND_BLINK_RUNTIME,
    KIND_FEATURE_PARAM,
    KIND_FLAG_ENTRY,
    KIND_IDL_INTERFACE,
    KIND_IDL_MEMBER,
    KIND_MOJO_INTERFACE,
    KIND_MOJO_METHOD,
    KIND_PREF,
    KIND_SWITCH,
    KIND_WEBUI_CONTROL,
    KIND_WEBUI_GATE,
    KIND_WEBUI_ROUTE,
    MODE_FORK,
    MODE_UPREV,
    MODES,
    MODIFIED,
    REMOVED,
    Change,
    Fact,
    Snapshot,
)

# Attributes whose change carries downstream meaning.  Anything outside this
# list is treated as bookkeeping.
MEANINGFUL_ATTRS: Dict[str, Tuple[str, ...]] = {
    # "conditions" matters because a vendor fork shadows upstream with a
    # build flag rather than editing it: the guard appearing or
    # disappearing is the change, while the value stays identical.
    # "var" is the C++ identifier. Downstream code writes `features::kFoo`,
    # never the feature string, so renaming the identifier while keeping the
    # string breaks our build -- and the string is what this fact is keyed on,
    # so without comparing "var" the change produces no finding at all.
    # Measured M130 -> M151: 4 such renames, including kDIPS -> kBtm.
    KIND_BASE_FEATURE: ("default_state", "platform_state", "conditions", "var"),
    KIND_FEATURE_PARAM: ("default", "type", "feature", "var"),
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
    ),
    KIND_IDL_INTERFACE: ("idl_kind", "inherits", "ext", "values"),
    KIND_IDL_MEMBER: ("signature", "member_type", "ext", "runtime_enabled"),
    # Effectively empty, and deliberately. "module" is part of the key, so it
    # can never differ; "methods" and "method_count" do change -- 107 times
    # across M130 -> M151 -- but every one of those is already a mojo_method
    # added or removed finding of its own. Comparing them here would report the
    # same ABI change twice, once vaguely and once precisely.
    KIND_MOJO_INTERFACE: ("module",),
    KIND_MOJO_METHOD: ("signature", "params", "response", "attrs"),
    # "platform_state" is the guard resolved for Windows, not the guard text:
    # a key entering or leaving our binary is the change, while upstream
    # tidying `!IS_ANDROID` off one is not. The raw `conditions` stay on the
    # fact, unread here, because the fork shadow analysis needs the text.
    KIND_SWITCH: ("var", "platform_state"),
    KIND_PREF: ("var", "platform_state"),
    KIND_FLAG_ENTRY: ("expiry_milestone",),
    KIND_WEBUI_ROUTE: ("route", "parent", "guards"),
    KIND_WEBUI_CONTROL: ("control", "pref", "label", "build_conditions"),
    KIND_WEBUI_GATE: ("expression", "features", "enabled_checks"),
}

# Base severity per (kind, change_type).  Impact scoring adjusts these using
# the downstream profile; these numbers only encode "how much does Chromium
# changing this normally matter".
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
    "killswitch_retired": 35,
    "experimental_dropped": 20,
    "web_api_signature_change": 50,
    "ipc_signature_change": 80,
    "ipc_removed": 75,
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

# MODE_UPREV / MODE_FORK / MODES are defined in model.py and re-exported here,
# because every stage downstream of this one -- scoring, prompts, reports --
# also has to know which comparison it is describing.
#
# Fork-mode signals. The question is not "did behaviour change" but "is this
# divergence we own, and what happens to it at the next rebase".
FORK_SIGNALS: Dict[str, int] = {
    "fork_dropped": 65,          # vendor removed something upstream has
    "fork_added": 45,            # vendor added something upstream lacks
    "fork_default_override": 60,  # vendor ships a different default
    "fork_modified": 45,         # vendor changed the declaration
    "fork_ui_removed": 60,       # vendor removed a page or control
    "fork_ui_added": 45,
}

FORK_LABELS: Dict[str, str] = {
    "fork_dropped": "We removed this; upstream still has it. A future rebase "
                    "reintroduces it unless the patch is carried",
    "fork_added": "We added this; upstream has no equivalent. Watch for "
                  "upstream shipping something that collides",
    "fork_default_override": "We ship a different default from upstream",
    "fork_modified": "We changed this declaration",
    "fork_ui_removed": "We removed this page or control",
    "fork_ui_added": "We added this page or control",
}


SIGNAL_LABELS: Dict[str, str] = {
    "enabled_by_default": "Now ON by default on Windows",
    "disabled_by_default": "Now OFF by default on Windows",
    "default_flip_on": "Default flipped on",
    "default_flip_off": "Default flipped off",
    "feature_deleted": "Feature flag deleted upstream",
    "flag_retired_on": "Shipped, then flag retired — behaviour is now permanent "
                       "and can no longer be turned off",
    "flag_retired_off": "Never shipped, flag and code removed — can no longer "
                        "be turned on",
    "new_feature_on_by_default": "New feature, on by default",
    "web_api_shipped": "Web API reached stable",
    "web_api_unshipped": "Web API pulled back from stable",
    "web_api_removed": "Web API removed",
    "web_api_added": "New web API surface",
    "killswitch_retired": "Kill-switch flag retired (feature now permanent)",
    "experimental_dropped": "Experimental flag dropped",
    "web_api_signature_change": "Web API signature changed",
    "ipc_signature_change": "Mojo method signature changed (ABI)",
    "ipc_removed": "Mojo interface/method removed",
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

# Fork-mode entries live in their own dicts above so the two vocabularies stay
# readable, then merge here so every consumer -- reports, prompts, scoring --
# looks signals up in one place.
SIGNAL_SEVERITY.update(FORK_SIGNALS)
SIGNAL_LABELS.update(FORK_LABELS)


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


def diff_snapshots(old: Snapshot, new: Snapshot, platform: str = PLATFORM,
                   target_milestone: Optional[int] = None,
                   mode: str = MODE_UPREV) -> List[Change]:
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

    old_index = old.index()
    new_index = new.index()

    changes: List[Change] = []

    for uid, new_fact in new_index.items():
        old_fact = old_index.get(uid)
        if old_fact is None:
            changes.append(_make_change(ADDED, None, new_fact, platform,
                                        target_milestone, mode=mode))
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
                                    target_milestone, deltas, mode=mode))

    for uid, old_fact in old_index.items():
        if uid not in new_index:
            changes.append(_make_change(REMOVED, old_fact, None, platform,
                                        target_milestone, mode=mode))

    if mode == MODE_UPREV:
        # Pairing a removal with an addition by C++ variable detects a rename
        # over time. Across a fork the same pattern means the vendor replaced
        # one thing with another, which is not a rename and must not be
        # collapsed into one.
        changes = _detect_renames(changes)
        # Same shape of problem as a rename, on a different identity: the part
        # of a control's key that moved is the preference it writes.
        changes = _detect_repointed_controls(changes)
    changes.sort(key=lambda c: (-c.severity, c.kind, c.key))
    return changes


def _make_change(change_type: str, old_fact: Optional[Fact],
                 new_fact: Optional[Fact], platform: str,
                 target_milestone: Optional[int],
                 deltas: Optional[Dict[str, List]] = None,
                 mode: str = MODE_UPREV) -> Change:
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
    )
    change.signals = _signals_for(change, old_fact, new_fact, platform,
                                  target_milestone, mode=mode)
    change.severity = _severity_for(change)
    return change


def _severity_for(change: Change) -> int:
    floor = max((SIGNAL_SEVERITY.get(s, 0) for s in change.signals), default=0)
    # A declaration that only moved file did not change behaviour, so the
    # per-kind base severity would overstate it. The signal governs instead.
    if change.change_type == MODIFIED and set(change.deltas) == {"path"}:
        return floor
    base = BASE_SEVERITY.get((change.kind, change.change_type), 20)
    return max(base, floor)


def _fork_signals(change: Change, platform: str) -> List[str]:
    """Divergence semantics: the vendor did this, not Chromium.

    Direction matters. The comparison is run as upstream -> fork, so a fact
    missing on the fork side is something *we* removed, not something upstream
    dropped.
    """
    kind = change.kind
    ui_kinds = (KIND_WEBUI_ROUTE, KIND_WEBUI_CONTROL, KIND_WEBUI_GATE)

    if change.change_type == REMOVED:
        return ["fork_ui_removed"] if kind in ui_kinds else ["fork_dropped"]
    if change.change_type == ADDED:
        return ["fork_ui_added"] if kind in ui_kinds else ["fork_added"]

    signals = ["fork_modified"]
    if kind in (KIND_BASE_FEATURE, KIND_BLINK_RUNTIME):
        states = change.deltas.get("platform_state") or change.deltas.get(
            "platform_status")
        flipped = False
        if isinstance(states, list) and len(states) == 2:
            old = states[0].get(platform) if isinstance(states[0], dict) else None
            new = states[1].get(platform) if isinstance(states[1], dict) else None
            flipped = old != new
        if flipped or "default_state" in change.deltas or "status" in change.deltas:
            signals.append("fork_default_override")
    return signals


def _signals_for(change: Change, old_fact: Optional[Fact],
                 new_fact: Optional[Fact], platform: str,
                 target_milestone: Optional[int],
                 mode: str = MODE_UPREV) -> List[str]:
    if mode == MODE_FORK:
        return _fork_signals(change, platform)

    signals: List[str] = []
    kind = change.kind

    if kind == KIND_BASE_FEATURE:
        signals += _base_feature_signals(change, old_fact, new_fact, platform)
    elif kind == KIND_BLINK_RUNTIME:
        signals += _blink_signals(change, old_fact, new_fact)
    elif kind in (KIND_IDL_MEMBER, KIND_IDL_INTERFACE):
        if change.change_type == REMOVED:
            signals.append("web_api_removed")
        elif change.change_type == ADDED:
            signals.append("web_api_added")
        else:
            if "signature" in change.deltas or "idl_kind" in change.deltas:
                signals.append("web_api_signature_change")
            # `inherits` moves the prototype chain, `values` adds or drops an
            # enum member -- both change what a site can write, and both were
            # compared without ever producing a row anyone could read.
            if "inherits" in change.deltas or "values" in change.deltas:
                signals.append("web_api_shape_changed")
            # Extended attributes and [RuntimeEnabled=] decide which contexts
            # the member exists in and which flag turns it on.
            if "ext" in change.deltas or "runtime_enabled" in change.deltas:
                signals.append("web_api_exposure_changed")
    elif kind in (KIND_MOJO_METHOD, KIND_MOJO_INTERFACE):
        if change.change_type == REMOVED:
            signals.append("ipc_removed")
        elif change.change_type == MODIFIED and (
                "signature" in change.deltas or "params" in change.deltas
                or "response" in change.deltas):
            signals.append("ipc_signature_change")
    elif kind == KIND_FEATURE_PARAM:
        if "default" in change.deltas:
            signals.append("param_default_changed")
        if "var" in change.deltas:
            signals.append("feature_symbol_renamed")
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
            # Windows build. Only the resolved verdict is compared, so upstream
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
        # unconditional. What breaks is a *downstream override* -- and the build,
        # if our source still names the symbol -- so both stay breaking signals
        # and the impact stage promotes them only when there is local evidence.
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
        # matters downstream if this browser was overriding the flag.  Real
        # API removals are detected from the IDL diff instead.
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

    if ("origin_trial_feature_name" in change.deltas
            or "origin_trial_allows_third_party" in change.deltas):
        signals.append("origin_trial_change")
    # What turns this flag on from inside the binary, and what it drags with
    # it. `base_feature` going to "none" means the C++ feature that used to
    # control it is gone.
    if any(a in change.deltas for a in ("base_feature", "base_feature_status",
                                        "depends_on", "implied_by", "public",
                                        "copied_from_base_feature_if")):
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
            paths=sorted(set(r.paths) | set(a.paths)), signals=signals,
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
