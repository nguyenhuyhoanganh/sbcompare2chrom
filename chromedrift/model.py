"""Core data model shared by every stage of the pipeline.

The pipeline is a straight line of pure data transforms:

    Snapshot(ref)  ->  [Fact]         extract/*
    (Snapshot, Snapshot) -> [Change]  diff.py
    [Change] -> [Finding]             score.py
    [Finding] -> [Finding+context]    cluster.py, enrich/*
    [Finding] -> report               report/*

It ends at the report on purpose.  Deciding what a change means for the
product is judgement, and it is left to whoever reads the report.

Every stage reads and writes JSON, so any stage can be run, cached, inspected
and re-run on its own.  That matters here because acquiring a snapshot costs
network time while the diff and scoring stages are iterated on constantly.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Bump whenever cached artifacts stop meaning what an older build thought they
# meant, so stale caches are rebuilt instead of silently misread.
#   2: extraction is scoped to the declared target set. Version 1 snapshots
#      took their scope from whatever the shared per-ref tree cache held, so a
#      "minimal" snapshot could contain the full fact set.
#   3: the "default" target set gained the desktop WebUI surfaces, so a
#      version 2 snapshot named "default" no longer means the same thing.
#   4: base_feature facts record the preprocessor guards enclosing them.
#      Snapshots without that attribute compare as different from ones with
#      it, which made an identical tree look 1,369 facts diverged.
#   5: WebUI templates include the Lit dialect (.html.ts). Version 4 read only
#      Polymer .html, leaving 23% of templates unread -- and nearly all of
#      extensions, print_preview, history, bookmarks and downloads.
#   6: the tree cache marker now includes the target's suffix filter. Version 5
#      snapshots were rebuilt over trees fetched under the old, narrower
#      filter, so they claim to cover Lit templates and do not.
#   7: the target set gained 13 feature files it had been missing, including
#      chrome_features.cc. Version 6 snapshots cover about 45% fewer
#      base::Feature declarations than they appear to.
#   8: the filename filter widened past the *_features.cc convention and now
#      excludes test files. Version 7 read 1 of 24 declarations in
#      chrome/browser/ui/webui and counted test-only features elsewhere.
#   9: the product is a Windows desktop browser, so platform is fixed rather
#      than selectable. platform_state/platform_status now carry only
#      "windows", and blink facts renamed android_status -> windows_status.
#  10: the legacy `const base::Feature kFoo{...}` form records "conditions"
#      like the macro form does. Version 9 omitted it there, so a feature
#      written the old way on one side of a comparison and the new way on the
#      other reported as modified when nothing had changed.
#  11: a WebUI control's identity is qualified by its element id when it has
#      one. The preference alone is not unique -- a radio group and its buttons
#      share it -- so 142 of 881 controls at M148 were being dropped as
#      duplicates, and which survived depended on directory walk order.
#  12: findings no longer carry an `ai` verdict. The tool stops at the evidence
#      and the ranking; judging what a change means is the reader's job, and
#      the reader is a human or an agent running the
#      `analyzing-chromium-uprevs` skill. A version 11 report may hold `ai`
#      blocks, which nothing here reads any more.
#  13: extraction honours a tree target's suffix filter, not just its path
#      prefix. Version 12 snapshots extracted whatever an earlier, wider run
#      had left under the prefix in the shared tree cache: at M148 that was 103
#      .mojom files under chrome/browser/ui/webui, which the "default" target
#      asks for as .cc only. Diffed against a clean M151 it produced 803
#      phantom "Mojo method removed" findings at severity 80 -- the tool's
#      highest -- sitting at the top of the report.
#  14: the target set reads every pref file in the tree, not just
#      chrome/common/pref_names.h. Version 13 snapshots hold 683 pref keys
#      where 1,575 exist, so 892 keys were absent -- and because Chromium is
#      actively splitting that file up, keys leaving it read as deletions.
#  15: four corrections found by auditing extraction and comparison against six
#      real versions (M130 through M151):
#        - a base::Feature's C++ identifier is compared. Version 14 keyed on
#          the feature string only, so renaming the identifier while holding
#          the string produced no change at all -- kDIPS -> kBtm among them,
#          which breaks the build of anything writing features::kDIPS.
#        - a WebUI control that starts writing a different preference is paired
#          and reported. Version 14 emitted two unconnected rows, because the
#          preference is part of the control's identity; 21 real repoints were
#          split that way.
#        - the `*_prefs.{h,cc}` naming convention is read as well as
#          `*pref_names.{h,cc}`, adding 469 keys in 54 files.
#        - a control's `pref` attribute requires the `prefs.` binding prefix,
#          so an ordinary component property is no longer recorded as a
#          preference key. 27 of 156 bindings at M151 were such properties.
#  16: every snapshot records how much of its version's tree the target set
#      actually read, measured against a recursive listing of that tree rather
#      than assumed. Version 15 snapshots carry no such measurement, and the
#      target set they were built from named files chosen at M151, which is a
#      different scope from the one the same name resolves to now.
#  17: `wide` reads every filename shape an extractor understands, not only
#      feature and pref files, and reaches content/ and blink/public. Version 16
#      downloaded the archives holding 934 of the tree's 1,424 .mojom files and
#      124 of its 132 WebUI surfaces, then discarded them for want of a suffix
#      in a filter. String constants are also read across platform trees now,
#      so a pref key moving into a ChromeOS file reads as a move rather than a
#      deletion.
#  18: filename hints match the bare spelling as well as the prefixed one.
#      Chromium writes both `content_switches.cc` and plain `switches.cc`, and
#      the hints required the underscore, so 44 files at M151 were fetched and
#      never read -- among them `components/embedder_support/switches.cc`,
#      which declares --headless, and `extensions/common/switches.cc`, which
#      declares 35 more. Version 17 snapshots are missing those switches while
#      reporting that they read every file in the tree. The candidate rule also
#      learned the `*flags.{cc,h}` convention, which the extractors already
#      read, so coverage now counts 31 files it used to leave out of its own
#      denominator.
#  19: one list of the filename shapes an extractor can read, and one name per
#      distinct measurement.
#        - `--complete` filtered its partition roots through a second copy of
#          that list, which had never learned the `*_prefs.{h,cc}` convention
#          or the `.h` half of four `.cc` hints. The flag whose whole promise is
#          "100% of these roots, by construction" skipped 86 files holding 747
#          keys at M151, so a version 18 `--complete` snapshot is missing them.
#        - a report's `summary.coverage` was area routing while a snapshot's
#          `meta.coverage` was tree coverage. It is now
#          `summary.area_coverage`, and `meta.coverage` in a report means the
#          same thing it means on a snapshot.
#  20: extraction stopped depending on the order the filesystem hands back
#      directories, and everything the comparison treats as meaningful now
#      produces a label.
#        - `os.walk` was sorted for files and not for directories, and when two
#          files declare the same fact the order decided which survived. 228
#          uids collide in the M151 tree and 68 disagree on a compared
#          attribute, so a version 19 snapshot is one of several possible
#          answers: walking the same tree twice in different orders and diffing
#          the result against itself produced 68 changes, topped by a
#          `web_api_signature_change` at severity 50. Dedupe now picks the
#          lowest (path, line) instead of the first arrival.
#        - preference and switch declarations record the `#if` chain around
#          them, resolved for Windows. 115 keys at M151 are not in our binary
#          at all, and nothing had marked them.
#        - WebUI controls record their GRIT `<if expr>` resolved the same way.
#        - a header's own include guard is no longer recorded as a build guard,
#          and an `#elif` branch carries the negation of the branches above it.
#        - a WebUI gate is identified by its handler as well as its
#          loadTimeData key, and a WebUI control by its declaring file as well
#          as its directory. Neither string was unique: at M151, 62 of 668 gate
#          keys were set by more than one handler and 98 of 1,256 control keys
#          declared in more than one file, so 318 declarations were dropped as
#          duplicates and which survived depended on walk order. This is the
#          same defect schema 11 fixed for a control's preference, one level
#          out. Recovering them moves the M151 default set from 24,679 facts to
#          24,871 and wide from 36,095 to 36,356.
#        - nine new signals label attributes that were compared and never
#          explained -- 380 of 709 modified changes at M148 -> M151.
#  21: every fact points at a line, and a finding carries the place rather than
#      only the file.
#        - four of the thirteen kinds set no line number at all -- every Mojo
#          method, every IDL member, every Blink runtime flag and every
#          chrome://flags entry, 20,844 of 36,356 facts. Mojo interfaces had
#          one and it was wrong: `\s*` after the newline in the interface
#          pattern crossed blank lines and masked comments, so 1,453 of 1,455
#          were reported at the last content line above the declaration.
#        - `Change` carries `locations` ("path:line"), and both renderers show
#          it. Version 20 reports cite a file and leave the reader to search it.
#        - the Web IDL reader is restricted to `third_party/blink/renderer/`.
#          The `.idl` extension is shared with Chrome Extensions IDL and with
#          MIDL, and it read both wrongly rather than not at all: 1,081 facts at
#          M151, 96 of them with a whole nested declaration inside their own
#          signature, all reported as Web API changes.
#  22: two curated lists that had decayed became rules, and every attribute the
#      comparison treats as meaningful now produces a label.
#        - a WebUI control is recognised by shape rather than by a list of 27
#          tag names. Measured at M151 across the eight surfaces the default
#          set reads, that list matched 902 of 2,462 custom-element occurrences
#          (36%), and 41 of the misses bind a real preference --
#          `settings-collapse-radio-button` writes one 27 times, and
#          `report/wording.py` already carried a word for that very tag, so the
#          renderer knew about a control the extractor never emitted. A version
#          21 snapshot holds 884 controls where 971 exist, 156 of them
#          preference-bound where 190 are, and 130 identified only by position
#          against 15 now.
#        - `BASE_FEATURE_PARAM` without a name string derives the name from the
#          variable, as `BASE_FEATURE` already did. 20 declarations at M151 are
#          written that way, and version 21 read the *default value* as the
#          param name and dropped the default: `kCacheCertVerificationTtlSecs`
#          came out as a param called `1800`, so changing 1800 to 3600 read as
#          one param removed and another added instead of a default moving.
#        - nine attributes were compared and never explained. A base::Feature's
#          `conditions` (55 rows in M143 -> M148), a Mojo method's `attrs`, a
#          Windows state moving to `conditional`, a feature param's type or
#          owning flag, an IDL member's `member_type`, and the three Blink
#          fields that decide who may reach a flag from outside the renderer.
#          `mojo_interface.module` was dropped from the compared set instead:
#          it is part of the key and can never differ.
#        - two more curated lists found by the same audit. A preference key
#          written `inline constexpr std::string_view kFoo = "..."` is read;
#          version 21 knew only the `char kFoo[]` spelling, so all 63 keys in
#          files Chromium has migrated -- `components/soda/pref_names.h`
#          entirely -- were invisible while the file itself counted as covered.
#          And the Blink manifest's `origin_trial_os`, `origin_trial_type`,
#          `origin_trial_allows_insecure` and `is_protected_feature` are
#          carried, which is 40 declarations at M151 deciding who may turn a
#          flag on from outside the binary.
#  23: the coverage measurement is graded against the tree instead of against
#      the ground it already covers.
#        - `DISCOVERY_ROOTS` was the fourteen roots the fetch targets happen to
#          live under, so the denominator was chosen by the same list it was
#          grading. `wide` scored 1,039 of 1,039 and reported **100%**, while
#          `chromedrift catalog`, which walks the real tree, counted 1,192
#          files the same rule says can declare. The 153 in the gap could never
#          appear as missed however wide the run: `base/base_switches.h`,
#          `base/features.cc`, `cc/base/features.cc`, `device/fido/public/
#          features.cc`, `sandbox/policy/features.cc`,
#          `google_apis/gaia/gaia_switches.cc`. Three of those files alone hold
#          88 base::Feature declarations nothing reads. This is the defect
#          schema 18 fixed one level down, where the filename rule was the
#          thing too narrow; here it was the ground the rule ran over. Fetching
#          is unchanged -- the roots feed the measurement only -- so a version
#          22 snapshot's coverage figure is the same reading taken against a
#          smaller denominator, and reads higher than the truth.
#        - vendored third-party projects are excluded by name rather than by
#          falling outside the roots, so `catalog` and the per-run measurement
#          describe one population and a test can hold them to it.
#        - a snapshot's `missing_targets` reaches the report. It was printed by
#          the run that built the snapshot and lost on every cached run after
#          it, and it was in none of the three report files.
#  24: `wide` reads every file the rule admits, so its figure means what it
#      says. Schema 23 made the denominator honest and the answer came back
#      88%; this closes the 139 it named. base/, device/, cc/, sandbox/,
#      storage/, google_apis/, pdf/, mojo/ and Blink's renderer/platform are
#      fetched -- 22 MB per version on top of 315 -- and the two Blink renderer
#      archives the default set already downloaded are filtered by everything
#      an extractor reads rather than by `.idl` alone, which was free.
#      Binaries that ship beside the browser rather than being it are excluded
#      by name instead: the headless shell, Chrome Remote Desktop, the updater,
#      the enterprise companion, the Windows services, and Fuchsia's own tree,
#      which the platform rule had missed by one suffix.
#  25: the tool compares one Chromium version against another and nothing
#      else, and the scoring answers a different question because of it.
#        - `--mode fork`, `--profile`, `discover` and `provenance` compared
#          this tree against a modified copy of it, and every one of them
#          needed a description of that copy which the tool cannot obtain on
#          its own. Without that description the scoring
#          degenerated: `Must fix` was unreachable by construction, and on a
#          real M148 -> M151 run 1,384 of 2,800 findings landed in "New
#          opportunity" because the rule for it was "anything added". A version
#          24 report carries `areas`, `matched_paths` and `matched_symbols` on
#          every finding, all three empty, and four bucket names that describe
#          a workflow nothing in the tool can support.
#        - severity comes from the signal when there is one, and from the kind
#          and direction only when there is not. It used to be the higher of
#          the two, so the coarse prior won whenever the precise statement was
#          lower: a Mojo method whose mojom attributes moved scored 75, the
#          same as one whose signature moved, because `(mojo_method, modified)`
#          is 75 and `build_gate_changed` is 35. Measured against two real
#          pairs, the prior overrode the signal on 267 of 2,800 findings at
#          M148 -> M151 and 345 of 6,787 at M143 -> M151, every one of them
#          upwards.
#        - a declaration Chromium excludes from the Windows build on *every*
#          side of the change scores zero rather than a fixed penalty, and one
#          that enters or leaves the build keeps its full severity. Version 24
#          read `after or before`, so a feature leaving our binary -- the case
#          that costs us the feature -- was scored *down* 45 points for not
#          being in our binary.
#        - a removal read from a tree the run did not finish reading is
#          discounted by the share it did not read. `pref_left_scan` exists
#          because absence from part of the tree is not evidence of deletion;
#          that reasoning applies to every removal and to every addition, and
#          it was written into one signal's severity as a constant instead.
#  26: the data half of the Mojo ABI is read. Only `interface` was extracted,
#      which is 1,581 of the 5,911 declarations in the M151 tree -- 26% -- and
#      a struct field changing type breaks deserialization on the far side of a
#      process boundary exactly the way a moved method parameter does, without
#      breaking the build either. Structs, unions and their fields become facts;
#      an enum becomes one fact carrying its member list, because members alone
#      are 17,061 declarations and adding one is Mojo's ordinary way of
#      extending a type, so a fact each would bury the report to say what a
#      `values` delta says in one row. Version 25 snapshots hold none of it.
#  27: Mojo declarations carry `platform_state`, so the build question is asked
#      on them too. It was asked on four of the sixteen kinds -- 2,264 of
#      29,118 facts at M151, none of them Mojo -- while mojom states the same
#      condition as an attribute: `[EnableIf=is_win]`, `[EnableIfNot=is_ios]`.
#      256 declarations in the M151 tree are `is_android` and 186 are `is_win`,
#      and a version 26 report scores an Android-only field changing type at 80
#      and prints it at the top of a Windows report. Conditions are inherited
#      from enclosing declarations, because an enum inside an
#      `[EnableIf=is_android]` struct is not in our binary either.
#  28: a declaration under a platform directory carries `platform_state` too.
#      Chromium excludes `chrome/browser/ash/` and `.../android/` in BUILD.gn
#      rather than with a preprocessor guard, so nothing inside them carries an
#      `#if` for the scanner to find and the path is the only evidence. Two
#      copies of the directory list existed, in `targets.py` and in
#      `extract/__init__.py`, and they disagreed about `android/`; neither was
#      read when scoring. On a wide M148 -> M151 run 164 findings were declared
#      under a platform we do not build and none scored zero, topped by
#      `AndroidNewMediaPicker` at 75 in Behaviour change. Stamped only when
#      every declaration of the uid is under such a directory, since five keys
#      at M151 are declared in both.
#  29: three things an outside review found, all of them facts the tool had
#      and did not use.
#        - the `#if` *around* a base feature reaches `platform_state`. It was
#          collected into `conditions` and never applied, so 441 features at
#          M151 sat under a guard excluding Windows and were recorded
#          `enabled` or `disabled` for Windows anyway.
#        - a Mojo method written `Foo@0(...)` produces a fact. The regex
#          required `(` straight after the name, so 269 declarations across 23
#          files at M151 produced nothing at all, silently.
#        - `/mac/` and `/linux/` join the platform directories, which is 79
#          more Mojo facts that are not in our build.
#  30: one eligibility policy for discovery and extraction, per-surface
#      coverage, and Mojo ordinals compared rather than merely extracted.
#      Version 29 read `/web_test/` files into the denominator and never into
#      a snapshot, excluded `hit_test_opaqueness.mojom` from the denominator
#      while extracting it, discounted a web API removal seen against a 99.8%
#      read exactly as hard as a preference removal seen against 1.7%, and
#      produced no change at all for `Foo@0` becoming `Foo@1`.
#  31: an IDL member carries its whole overload set. Deduplication kept one
#      declaration of a name, so a sibling overload appearing or disappearing
#      moved nothing the diff could see: at M148 -> M151, 121 members have
#      more than one signature, 56 had that set change, and 2 were silent --
#      one of them `Document.parseHTMLUnsafe` losing an argument list, which
#      is a web API disappearing.
#  32: three more places where a fact was recorded and not compared, and one
#      normalisation. `platform_state` reached the diff on three of the
#      sixteen kinds, so a Mojo method or a settings control leaving the
#      Windows build produced no row. An IDL signature kept the space
#      Chromium puts after an opening parenthesis when it wraps a long
#      argument list, so seven SubtleCrypto members read as changed
#      signatures at 50 points on M148 -> M151 with nothing moved. And an
#      overload set gaining an entry at an argument count something already
#      had can take a call from it, which version 31 called harmless.
#  33: an overload set carries the gate on each overload, where they differ.
#      Version 32 kept only the signature strings, so a `[RuntimeEnabled]`
#      moving on one overload of a member was visible only if deduplication
#      happened to keep that declaration. 12 of the 121 overload groups at
#      M151 have overloads that disagree about their gate.
SCHEMA_VERSION = 33

# ---------------------------------------------------------------------------
# Fact kinds.  Each is produced by exactly one extractor.
# ---------------------------------------------------------------------------

KIND_BASE_FEATURE = "base_feature"
KIND_FEATURE_PARAM = "feature_param"
KIND_BLINK_RUNTIME = "blink_runtime_feature"
KIND_IDL_INTERFACE = "idl_interface"
KIND_IDL_MEMBER = "idl_member"
KIND_MOJO_INTERFACE = "mojo_interface"
KIND_MOJO_METHOD = "mojo_method"
# The data half of the same ABI. An interface says which calls cross a process
# boundary; a struct says what travels along them, and a field changing type
# breaks deserialization on the far side exactly the way a moved parameter does.
KIND_MOJO_STRUCT = "mojo_struct"
KIND_MOJO_FIELD = "mojo_field"
KIND_MOJO_ENUM = "mojo_enum"
KIND_SWITCH = "switch"
KIND_PREF = "pref"
KIND_FLAG_ENTRY = "flag_entry"
# Desktop WebUI. Settings, History, Downloads, Bookmarks, Extensions and ~130
# other chrome:// pages are all built the same way, and form one chain:
#   route -> loadTimeData guard -> base::Feature
KIND_WEBUI_ROUTE = "webui_route"
KIND_WEBUI_CONTROL = "webui_control"
KIND_WEBUI_GATE = "webui_gate"

ALL_KINDS = (
    KIND_BASE_FEATURE,
    KIND_FEATURE_PARAM,
    KIND_BLINK_RUNTIME,
    KIND_IDL_INTERFACE,
    KIND_IDL_MEMBER,
    KIND_MOJO_INTERFACE,
    KIND_MOJO_METHOD,
    KIND_MOJO_STRUCT,
    KIND_MOJO_FIELD,
    KIND_MOJO_ENUM,
    KIND_SWITCH,
    KIND_PREF,
    KIND_FLAG_ENTRY,
    KIND_WEBUI_ROUTE,
    KIND_WEBUI_CONTROL,
    KIND_WEBUI_GATE,
)

# Human labels used in reports.
KIND_LABELS = {
    KIND_BASE_FEATURE: "Chromium feature flag",
    KIND_FEATURE_PARAM: "Feature parameter",
    KIND_BLINK_RUNTIME: "Blink runtime feature",
    KIND_IDL_INTERFACE: "Web IDL interface",
    KIND_IDL_MEMBER: "Web IDL member",
    KIND_MOJO_INTERFACE: "Mojo interface",
    KIND_MOJO_METHOD: "Mojo method",
    KIND_MOJO_STRUCT: "Mojo struct",
    KIND_MOJO_FIELD: "Mojo struct field",
    KIND_MOJO_ENUM: "Mojo enum",
    KIND_SWITCH: "Command-line switch",
    KIND_PREF: "Preference",
    KIND_FLAG_ENTRY: "chrome://flags entry",
    KIND_WEBUI_ROUTE: "WebUI page",
    KIND_WEBUI_CONTROL: "WebUI control",
    KIND_WEBUI_GATE: "WebUI visibility gate",
}

# The sixteen kinds are not sixteen kinds of "feature", and reading them as
# though they were is the most common misreading of a report. They fall into
# three groups that differ in what a change to them *means*:
#
#   switches   the only group where a change moves behaviour on its own
#   contracts  a change breaks something outside the binary, silently -- stored
#              user data, launch scripts, live websites, the other process
#   surface    a change moves what the user sees, or moves a removal date
#
# Measured on a real M139 -> M143 report: 3,120 findings split 34% / 35% / 30%,
# so two thirds of a report is *not* about features being turned on or off.
# A flat kind list hides that, which is why the report groups its filter.
KIND_GROUP_SWITCH = "Behaviour switches"
KIND_GROUP_CONTRACT = "External contracts"
KIND_GROUP_SURFACE = "UI and scheduling"

KIND_GROUPS = (
    (KIND_GROUP_SWITCH, (KIND_BASE_FEATURE, KIND_FEATURE_PARAM, KIND_BLINK_RUNTIME)),
    (KIND_GROUP_CONTRACT, (KIND_PREF, KIND_SWITCH, KIND_IDL_INTERFACE,
                           KIND_IDL_MEMBER, KIND_MOJO_INTERFACE, KIND_MOJO_METHOD,
                           KIND_MOJO_STRUCT, KIND_MOJO_FIELD, KIND_MOJO_ENUM)),
    (KIND_GROUP_SURFACE, (KIND_WEBUI_ROUTE, KIND_WEBUI_CONTROL, KIND_WEBUI_GATE,
                          KIND_FLAG_ENTRY)),
)


# What a change in each group *means*, in one sentence. Kept beside the groups
# rather than in a renderer because both reports print it and a reader who only
# sees the group name learns nothing from it.
KIND_GROUP_MEANINGS = {
    KIND_GROUP_SWITCH: "The only group where a change moves behaviour on its "
                       "own. What our build does is different after this.",
    KIND_GROUP_CONTRACT: "A change here breaks something outside the binary, "
                         "and silently: data already on a user's disk, launch "
                         "scripts, live websites, the other process.",
    KIND_GROUP_SURFACE: "A change here moves what the user sees, or moves the "
                        "date something is scheduled to be removed.",
}


def group_of(kind: str) -> str:
    """Which of the three groups a fact kind belongs to."""
    for name, kinds in KIND_GROUPS:
        if kind in kinds:
            return name
    return ""


# ---------------------------------------------------------------------------
# Who has to do something about it.
#
# A third axis, and the only one that answers "is this mine". The bucket says
# how bad, the group says what kind of consequence, and neither tells the
# person reading whether to keep reading: a Mojo signature change and a
# settings control being relabelled are both "external contracts" to one
# reader and two entirely different jobs on two different desks.
#
# Decided by surface, except where the fix is somewhere else than the
# declaration. A renamed Finch string is a C++ edit nobody has to make and a
# server-side config nobody can see from here, so it is owned by whoever holds
# the configs rather than by whoever owns the file it was declared in.
# ---------------------------------------------------------------------------

OWNER_NATIVE = "native"
OWNER_WEBUI = "webui"
OWNER_WEBPLATFORM = "webplatform"
OWNER_IPC = "ipc"
OWNER_CONFIG = "config"

OWNER_ORDER = [OWNER_IPC, OWNER_WEBPLATFORM, OWNER_NATIVE, OWNER_WEBUI,
               OWNER_CONFIG]

OWNER_LABELS = {
    OWNER_NATIVE: "Browser C++",
    OWNER_WEBUI: "WebUI front-end",
    OWNER_WEBPLATFORM: "Web platform",
    OWNER_IPC: "Process boundaries",
    OWNER_CONFIG: "Outside the repository",
}

OWNER_MEANINGS = {
    OWNER_IPC: "Mojo interfaces, methods and the data that travels along "
               "them. Nothing here breaks the build: a mismatch shows up in "
               "generated bindings on the far side of a process boundary, so "
               "anything implementing or calling one of these has to be "
               "checked by hand.",
    OWNER_WEBPLATFORM: "What a web page can call. Blink IDL and the runtime "
                       "flags gating it. A removal here breaks live sites; an "
                       "addition still behind a closed flag breaks nothing "
                       "yet.",
    OWNER_NATIVE: "Feature flags, preferences and command-line switches "
                  "compiled into the browser. Renames here stop the build, "
                  "which is the easy case; a preference key that moved stops "
                  "nothing and orphans what users already have on disk.",
    OWNER_WEBUI: "The chrome:// screens: route tables, HTML templates and the "
                 "loadTimeData booleans gating them. A control that vanished "
                 "usually moved behind a flag rather than being removed.",
    OWNER_CONFIG: "The fix is not in this repository. Server-side Finch "
                  "configs, launch scripts, test automation and enterprise "
                  "policy, all of which keep working and quietly stop having "
                  "an effect. Nothing in the tool can see whether anyone was "
                  "relying on these, which is why they are listed rather than "
                  "scored.",
}

KIND_OWNERS = {
    KIND_BASE_FEATURE: OWNER_NATIVE,
    KIND_FEATURE_PARAM: OWNER_NATIVE,
    KIND_PREF: OWNER_NATIVE,
    KIND_SWITCH: OWNER_NATIVE,
    KIND_FLAG_ENTRY: OWNER_NATIVE,
    KIND_BLINK_RUNTIME: OWNER_WEBPLATFORM,
    KIND_IDL_INTERFACE: OWNER_WEBPLATFORM,
    KIND_IDL_MEMBER: OWNER_WEBPLATFORM,
    KIND_MOJO_INTERFACE: OWNER_IPC,
    KIND_MOJO_METHOD: OWNER_IPC,
    KIND_MOJO_STRUCT: OWNER_IPC,
    KIND_MOJO_FIELD: OWNER_IPC,
    KIND_MOJO_ENUM: OWNER_IPC,
    KIND_WEBUI_ROUTE: OWNER_WEBUI,
    KIND_WEBUI_CONTROL: OWNER_WEBUI,
    KIND_WEBUI_GATE: OWNER_WEBUI,
}


ADDED = "added"
REMOVED = "removed"
MODIFIED = "modified"


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """One extracted, normalized piece of the Chromium feature surface.

    ``key`` must be stable across Chromium versions even when the *syntax*
    that declares it changes.  This is not hypothetical: between M139 and M143
    the ``BASE_FEATURE`` macro dropped its string-name argument, so a parser
    keyed on raw source text reports every feature as removed-and-re-added.
    Extractors are responsible for normalizing to a semantic key.
    """

    kind: str
    key: str
    name: str
    path: str = ""
    line: int = 0
    attrs: Dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.kind}:{self.key}"

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "key": self.key, "name": self.name}
        if self.path:
            d["path"] = self.path
        if self.line:
            d["line"] = self.line
        if self.attrs:
            d["attrs"] = self.attrs
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(
            kind=d["kind"],
            key=d["key"],
            name=d.get("name", d["key"]),
            path=d.get("path", ""),
            line=d.get("line", 0),
            attrs=d.get("attrs", {}) or {},
        )


@dataclass
class Snapshot:
    """The complete extracted feature surface of one Chromium ref."""

    ref: str
    facts: List[Fact] = field(default_factory=list)
    milestone: Optional[int] = None
    created: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created:
            self.created = _dt.datetime.now(_dt.timezone.utc).isoformat(
                timespec="seconds"
            )

    def index(self) -> Dict[str, Fact]:
        """uid -> Fact.  Later duplicates lose; extractors dedupe first."""
        return {f.uid: f for f in self.facts}

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.facts:
            out[f.kind] = out.get(f.kind, 0) + 1
        return dict(sorted(out.items()))

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "ref": self.ref,
            "milestone": self.milestone,
            "created": self.created,
            "meta": self.meta,
            "counts": self.counts(),
            "facts": [f.to_dict() for f in self.facts],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        return cls(
            ref=d["ref"],
            milestone=d.get("milestone"),
            created=d.get("created", ""),
            meta=d.get("meta", {}) or {},
            facts=[Fact.from_dict(x) for x in d.get("facts", [])],
        )


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


@dataclass
class Change:
    """A semantic difference between two snapshots, for one Fact identity."""

    change_type: str  # added | removed | modified
    kind: str
    key: str
    name: str
    before: Optional[dict] = None
    after: Optional[dict] = None
    deltas: Dict[str, List[Any]] = field(default_factory=dict)  # attr -> [old, new]
    paths: List[str] = field(default_factory=list)
    # "path:line" per side. Separate from `paths` because a reader needs the
    # place, not just the file: content_features.cc declares nearly two hundred
    # features, so citing it leaves the reader to do the finding. Every
    # extractor had been computing a line number and nothing carried it past
    # the snapshot.
    locations: List[str] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)
    severity: int = 0

    @property
    def uid(self) -> str:
        return f"{self.kind}:{self.key}"

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type,
            "kind": self.kind,
            "key": self.key,
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "deltas": self.deltas,
            "paths": self.paths,
            "locations": self.locations,
            "signals": self.signals,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Change":
        return cls(
            change_type=d["change_type"],
            kind=d["kind"],
            key=d["key"],
            name=d.get("name", d["key"]),
            before=d.get("before"),
            after=d.get("after"),
            deltas=d.get("deltas", {}) or {},
            paths=d.get("paths", []) or [],
            locations=d.get("locations", []) or [],
            signals=d.get("signals", []) or [],
            severity=d.get("severity", 0),
        )


# ---------------------------------------------------------------------------
# Findings (a change, ranked)
# ---------------------------------------------------------------------------

# Four buckets, and every one of them is decidable from the change itself.
#
# The previous four -- Must fix / Needs review / New opportunity / FYI -- asked
# "what does this cost *us*", which needs a description of what "us" is. That
# description came from a profile naming a second, modified tree, and with
# that gone the question has no answer: `Must fix` required symbol evidence, so it
# was unreachable, and `New opportunity` was "anything added", so it took 1,384
# of 2,800 findings on a real M148 -> M151 run. A bucket that cannot be filled
# and a bucket that takes half the report are the same failure.
#
# These four answer the question the tool can actually answer -- **what kind of
# thing happened** -- and they come from the signal that set the severity, so a
# finding is filed under the sentence it is ranked by.
BUCKET_BREAKING = "breaking"
BUCKET_BEHAVIOUR = "behaviour"
BUCKET_NEW = "new"
BUCKET_HOUSEKEEPING = "housekeeping"

BUCKET_ORDER = [BUCKET_BREAKING, BUCKET_BEHAVIOUR, BUCKET_NEW,
                BUCKET_HOUSEKEEPING]

BUCKET_LABELS = {
    BUCKET_BREAKING: "Breaking",
    BUCKET_BEHAVIOUR: "Behaviour change",
    BUCKET_NEW: "New surface",
    BUCKET_HOUSEKEEPING: "Housekeeping",
}

BUCKET_MEANINGS = {
    BUCKET_BREAKING: "Something outside the binary stops working, and nothing "
                     "warns you: stored user data, launch scripts, Finch "
                     "configs, live websites, the other process.",
    BUCKET_BEHAVIOUR: "The Windows build behaves differently after this. "
                      "Someone can see a difference.",
    BUCKET_NEW: "Surface that did not exist before. Nothing is switched on by "
                "it on its own.",
    BUCKET_HOUSEKEEPING: "Chromium tidying up after itself, and scheduling. "
                         "Nothing observable moved, or the tool cannot tell "
                         "that anything did.",
}


@dataclass
class Finding:
    """A change plus its rank, and the reasons behind the rank.

    ``reasons`` is not decoration. The rank decides what a reader sees first,
    which is the whole value of it, so a reader has to be able to see why a row
    is where it is and argue with it. A ranking nobody can audit gets ignored
    the first time it is wrong.
    """

    change: Change
    reasons: List[str] = field(default_factory=list)
    score: int = 0
    bucket: str = BUCKET_HOUSEKEEPING
    enrichment: Dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.change.uid

    def to_dict(self) -> dict:
        return {
            "change": self.change.to_dict(),
            "reasons": self.reasons,
            "score": self.score,
            "bucket": self.bucket,
            "enrichment": self.enrichment,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(
            change=Change.from_dict(d["change"]),
            reasons=d.get("reasons", []) or [],
            score=d.get("score", 0),
            bucket=d.get("bucket", BUCKET_HOUSEKEEPING),
            enrichment=d.get("enrichment", {}) or {},
        )


@dataclass
class Report:
    """Full pipeline output for one comparison (from_ref -> to_ref)."""

    from_ref: str
    to_ref: str
    findings: List[Finding] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def bucket_counts(self) -> Dict[str, int]:
        out = {b: 0 for b in BUCKET_ORDER}
        for f in self.findings:
            out[f.bucket] = out.get(f.bucket, 0) + 1
        return out

    def by_bucket(self, bucket: str) -> List[Finding]:
        return [f for f in self.findings if f.bucket == bucket]

    def by_owner(self, owner: str) -> List[Finding]:
        """Findings routed to one desk, in the order they were ranked.

        Here rather than in either renderer so the two of them cannot disagree
        about who owns a row -- the failure this project keeps having is one
        fact derived twice.
        """
        from .diff import owner_of  # circular at module scope: diff imports us
        return [f for f in self.findings if owner_of(f.change) == owner]

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "from_ref": self.from_ref,
            "to_ref": self.to_ref,
            "summary": self.summary,
            "meta": self.meta,
            "bucket_counts": self.bucket_counts(),
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Report":
        return cls(
            from_ref=d["from_ref"],
            to_ref=d["to_ref"],
            findings=[Finding.from_dict(x) for x in d.get("findings", [])],
            summary=d.get("summary", {}) or {},
            meta=d.get("meta", {}) or {},
        )


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def write_json(path: str, obj: Any) -> str:
    """Write ``obj`` as UTF-8 JSON, creating parent directories."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)
    os.replace(tmp, path)
    return path


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# Kinds where two declarations of one name are the language working rather
# than an accident. Web IDL overloads a member by argument list, so
# `Navigator.install()` and `Navigator.install(InstallParams)` are two real
# members with one name; keeping only the lowest hid an overload appearing or
# disappearing. Measured M148 -> M151 with 121 such members: 56 had their
# overload set change and 2 were invisible, one of them an overload being
# removed -- which is a web API disappearing, the thing this kind scores 70
# for when it can see it.
#
# The surviving fact carries the whole set, the way `mojo_enum` carries its
# member list rather than becoming a fact per member.
_OVERLOADED_KINDS = frozenset({"idl_member"})


def dedupe_facts(facts: Iterable[Fact]) -> List[Fact]:
    """Drop duplicate uids, keeping the declaration lowest in path order.

    Chromium declares the same thing in more than one place far more often than
    it looks: 228 uids in the M151 tree, and 68 of those disagree on an
    attribute the diff compares. ``switch:disabled`` is declared by three
    different C++ constants in three files, none of them the same switch.

    Which copy survives therefore has to be decided by a rule, not by arrival.
    It used to be "first seen", and first was whatever ``os.walk`` handed back
    first -- filesystem order, which differs between machines and between the
    two trees of a single comparison. Diffing the M151 tree against itself under
    two walk orders produced 68 changes describing nothing, topped by a
    ``web_api_signature_change`` at severity 50.

    Lowest ``(path, line)`` is arbitrary in the same way "first" was, but it is
    a property of the tree rather than of the machine reading it, so two runs
    anywhere agree. The walk is sorted as well, so ordering never reaches here.
    """
    best: Dict[str, Fact] = {}
    overloads: Dict[str, set] = {}
    for f in facts:
        if f.kind in _OVERLOADED_KINDS:
            signature = f.attrs.get("signature")
            if signature:
                overloads.setdefault(f.uid, set()).add(
                    (signature, f.attrs.get("runtime_enabled", "")))
        current = best.get(f.uid)
        if current is None or (f.path, f.line) < (current.path, current.line):
            best[f.uid] = f
    for uid, entries in overloads.items():
        signatures = {sig for sig, _ in entries}
        if len(signatures) > 1:
            # Recorded only when there is more than one, so an ordinary member
            # compares exactly as it always did.
            best[uid].attrs["signatures"] = sorted(signatures)
        # And the gate per overload, but only where the overloads disagree
        # about it -- 12 of the 121 groups at M151. Kept as its own attribute
        # rather than folded into the signature string: a gate moving is an
        # overload changing who can reach it, and encoding it into the
        # identity would report the same event as one overload disappearing
        # and another arriving.
        gates = {gate for _, gate in entries}
        if len(gates) > 1:
            best[uid].attrs["overload_gates"] = sorted(
                f"{sig} [{gate or 'ungated'}]" for sig, gate in entries)
    return sorted(best.values(), key=lambda f: (f.kind, f.key))
