---
name: analyzing-chromium-uprevs
description: Compares Chromium versions for a downstream browser fork - feature flags, web APIs, prefs, switches, Mojo interfaces, settings surface - separating real behaviour changes from upstream cleanup, and also compares the fork itself against the upstream release it was merged from to find carried divergence and merge debt. Produces a triaged report of what the fork must fix. Use when planning or reviewing a Chromium uprev such as M148 to M151, when asked what is new, removed, or changed between two Chromium milestones, when asked how a fork such as Samsung Browser differs from the Chromium it is based on, when asked which upstream features the fork never took or silently lost across merges, when interpreting a raw Chromium diff, or when deciding what work a rebase requires.
---

# Analyzing Chromium uprevs

Compare two Chromium versions from a downstream fork's point of view and report
what the team must actually do.

Finding differences is easy and useless: a four-milestone gap changes millions
of lines. **Most apparent changes are not changes.** This skill's main job is to
stop confident wrong conclusions.

## The rule that governs everything

Chromium gates every feature behind a flag and moves it through three stages,
normally **several milestones apart**:

| Stage | Code | Users see |
|---|---|---|
| A | New code lands, flag default OFF | nothing |
| B | Flag default flips ON | **the change** |
| C | Old path and flag deleted | nothing |

So a diff between two versions mostly shows stages A and C. **A code change and
a user-visible change almost never land in the same milestone.**

Therefore never report "X changed" alone. Always answer two separate questions:

1. Did the **flag state** change on our platform? → behaviour changed
2. Did only **code** change? → cleanup; matters only if we reference the symbol

These are two lists with different owners and urgency. Keep them separate.

## Workflow

Copy this checklist and track progress:

```
- [ ] 1. Confirm platform, exact versions, and profile
- [ ] 2. Run chromedrift
- [ ] 3. Triage Must fix and Needs review
- [ ] 4. Classify each finding (decision procedure below)
- [ ] 5. Write the report, including limits
```

### Step 1: Confirm inputs

Ask for anything missing.

- **Which comparison.** Two Chromium versions (an uprev), or upstream against
  the fork (divergence)? They use the same engine and opposite vocabularies —
  see *Comparing the fork* below. Ask if it is not stated; the answer changes
  what every "removed" in the output means.
- **Platform** is fixed to Windows and is not a question. There is no
  `--platform` flag: Chromium wraps defaults in `#if BUILDFLAG(IS_WIN)`, so
  reading the wrong platform inverts conclusions rather than blurring them, and
  an option nobody checks is a way to be silently wrong. Read
  `platform_state.windows`, never `default_state`.
- **Exact versions**, never bare milestone numbers. `151` resolves to whatever
  is newest stable today and drifts between runs. Real example:
  `ServiceWorkerAutoPreload` is ENABLED in 143.0.7499.40 and DISABLED in
  143.0.7499.194 — same milestone, different patch release.
- **Downstream profile** (`config/sb-profile.json5`) pointing at real patches or
  fork source. Without it **nothing can reach Must fix**, and a report showing
  `must fix: 0` means "no evidence supplied", not "clean uprev".

### Step 2: Run

```bash
python3 -m chromedrift check          # verify machine, network, configs

python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --profile config/sb-profile.json5 \
  --out out/M148_to_M151
```

Pure Python 3.9+ stdlib, no install, no Chromium checkout (pulls ~40 MB of
declaration files per version). Cold run about two minutes; cached runs seconds.

Outputs: `report.md` (paste into a ticket), `report.html` (filterable, fully
self-contained), `report.json` (scripting). Every finding cites `path:line` on
each side, under `change.locations` in the JSON -- quote it, do not paraphrase
the file name.

**The tool does not judge.** It stops at extracted evidence and a deterministic
rank; deciding what a change means for the product is your job, and this skill
is the procedure for it. Nothing in the report is a verdict, so there is no
verdict column to mistake for a clean result — but equally, an empty **Must
fix** means "no evidence was supplied", never "nothing to do".

Options: `--no-enrich` skip network lookups, `--mode fork` compare against a
fork instead of across time, and `--target-set` to choose how much is read:

| | Per version | Files read | Use for |
|---|---:|---:|---|
| `minimal` | ~1 MB | 3 | smoke test |
| `default` | ~40 MB | 4% of files, over half the flags | day to day |
| `wide` | 315 MB fetched, 94 MB kept | **100% of files** | release gate |

**Every run prints the coverage it achieved**, measured against a listing of
that version's own tree rather than assumed:

```
coverage: reads 42 of 1039 files in this tree that could declare (4% of files)
  largest gaps: chrome/browser/ (251 files), components/enterprise/ (50 files)
```

Read that line before reading the findings. A hand-written list of target files
decays — built as it stood at M130 and run at M151 it misses 27% of the pref
files and 34% of the feature files that exist there — so the number is measured
every time rather than written down once.

The same measurement is in `report.json` under `meta.coverage`, as
`{from, to}` — one per side, each with `candidates`, `read`, `missed` and
`missed_by_directory` — with up to 400 unread paths from the TO side under
`meta.uncovered_files`. It is also the last block of `report.md`, under *How
this was produced*. Do not read `summary.area_coverage` for this: that is where
findings landed by area, a different measurement that happens to be about
coverage of something else.

`--partition settings` (repeatable: `downloads`, `bookmarks`, `history`,
`extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`,
`media`) limits what is fetched and scanned. Measured at M151 on the default
set: full run 24,871 facts, `--partition settings` 4,662. A partitioned run
prints its own coverage line, scoped to the partition's roots. **Faster and less
complete, one-directionally** — Chromium is not organized by product, so a
change affecting downloads can live in `content/` or in a Mojo interface and
match no partition. Right while iterating on one surface, wrong as a release
gate.

Other commands: `chromedrift report <report.json> --area <id>` re-renders one
team's slice without re-running anything; `chromedrift catalog <ref>` measures
what the target set is *missing* rather than guessing; `chromedrift provenance`
is described below.

### Step 3: Triage

Read **Must fix**, then **Needs review**. Skip **FYI** unless searching for a
specific symbol.

Bucket comes from *evidence*, not severity: Must fix requires that the profile
shows the fork references the symbol.

Before reading rows, read **What happened**. Both reports group every finding
under the signal that set its severity, so a 2,792-row report is about forty
things -- *Now ON by default on Windows* (77), *Mojo method signature changed
(ABI)* (40), *Preference no longer in the file we read* (139). Each is a
partition, not a highlight reel: every finding appears under exactly one, so the
counts are the report. That tells you what the milestone did before you have
read a single identifier, and it is grouped by the three consequence groups --
behaviour switches, external contracts, UI and scheduling -- so the two thirds
of a report that is *not* about features being turned on or off is visible as
its own set. Findings on `chrome://` surfaces are grouped by screen instead,
which is the axis that carries their meaning.

### Step 4: Classify each finding

Stop at the first question that settles it.

1. **Did the flag state change on our platform?** Check `platform_state` in the
   finding. `disabled → enabled` or the reverse is a real behavioural change.
   Report and stop.
2. **Did the flag disappear?** Check the state it held *before*. Signals
   `flag_retired_on` / `flag_retired_off` mean behaviour did not change here.
   Remaining question is only whether we reference it.
3. **Do we reference it?** `we_patch` / `we_reference` fields. If yes there is
   work regardless of behaviour: a build break, or an override that now
   silently does nothing.
4. **Is it a rename?** `feature_string_renamed`, `pref_renamed`,
   `switch_renamed` compile fine and fail silently in the field. Always
   actionable if the old name appears anywhere, including server-side Finch
   configs, launch scripts and test automation, which the tool cannot see.
5. Otherwise it is upstream churn. Record, do not escalate.

In `--mode fork` this procedure does not apply: there is no "before and after",
only "ours and theirs". Use the fork procedure in
**[reference/fork-comparison.md](reference/fork-comparison.md)** instead.

Signal meanings: **see [reference/signals.md](reference/signals.md)**.

### Step 5: Report

Structure, in this order:

1. **Verdict** — one sentence on the risk of this uprev
2. **Behavioural changes** — flag state actually moved on our platform
3. **Build and integration breaks** — symbols we reference, removed or renamed
4. **Silent breaks** — renames that compile cleanly and fail in the field
5. **New capability** — what we could adopt; product input, not a blocker
6. **Limits** — what was not examined

In `--mode fork` replace 5 with **Divergence to carry** — what a rebase would
silently undo — and say which findings are debt rather than decisions.

Always state the exact versions compared, and which partitions were scanned if
the run was partitioned.

Every finding needs three parts: **what moved**, **whether users see a
difference**, **what we must do**. The middle part decides priority and a raw
diff cannot supply it.

Bad: *"`LocalNetworkAccessChecksSplitPermissions` was removed in M151."*

Good: *"Local Network Access moved to split permissions. The flag was already
ENABLED at M148, so users saw this before our current base; M151 only retires
the flag. No behavioural change for us. Action: update any reference to
`kLocalNetworkAccessChecksSplitPermissions` or the `/localNetworkAccess`
route."*

The report carries evidence, not conclusions. Every finding shows its score
reasoning, its declaring paths and whether the fork references it, precisely so
a conclusion can be argued with — cite those fields rather than restating the
score.

`report.json` also carries `summary.milestone_brief`: Chromium's own account of
what shipped across the milestones being adopted, from chromestatus. Use it to
explain *why* something changed. It is **not** matched to the findings — the
names are prose and the findings are identifiers — so never pair a brief entry
with a finding unless the evidence in the finding itself supports it.

## Known traps

Every one of these produced a wrong conclusion before it was handled. Read
**[reference/traps.md](reference/traps.md)** before interpreting any removal.

Summary: retired flags read as removed features; declarations that moved read
as deleted; a macro migration that renamed features nobody edited;
platform-divergent defaults; declarative files that declare more than ships.

## Comparing the fork against upstream

A different question from an uprev, and the more common one for a long-lived
fork: not "what did Chromium change" but "what is different about us, and did
anyone decide that".

```bash
# What differs, right now, at the same milestone
python3 -m chromedrift run 148.0.7778.217 sb-main-dev --mode fork \
  --to-src /path/to/sbrowser/src --profile config/sb-profile.json5

# Decision or debt? Compare against the series we merged through
python3 -m chromedrift provenance sb-main-dev 131.0.x 139.0.x 148.0.7778.217 \
  --fork-src /path/to/sbrowser/src --profile config/sb-profile.json5
```

Direction is fixed as **upstream → fork**, so "removed" means *we* removed it
and "added" means *we* carry it. Nothing is an opportunity.

Two results a two-way diff cannot produce on its own:

- **Decision vs debt.** If our value matches an *older* Chromium exactly, nobody
  decided anything — we are stale, and the report names the milestone we are
  stuck on. Matching no upstream version means someone wrote it.
- **Shadowing.** A fork of this shape does not overwrite Chromium; it keeps its
  code beside upstream's behind `#if defined(SBROWSER_*)`. Both ship, so
  comparing values finds nothing: upstream's branch really is untouched, and the
  branch that runs is ours. Needs `vendor_markers` in the profile — without them
  the analysis is skipped rather than guessed.

Procedure, states and how to read both tables:
**see [reference/fork-comparison.md](reference/fork-comparison.md)**.

## Scoping to settings

Desktop settings are a WebUI page built from TypeScript and HTML templates.
Sources, the three-hop chain from a settings page to the flag behind it, and how
to size a "feature" (control / page / capability):
**see [reference/settings-surface.md](reference/settings-surface.md)**.

## What the tool cannot see

State these limits in every report. A clean report does not imply a clean uprev.

- **Implementation-only changes.** The tool reads declarations (macros, IDL,
  mojom, string constants, JSON/JSON5 manifests). Behaviour changed entirely
  inside a function body is invisible.
- **Coverage depends on which target set was run, and every run prints its
  own number.** Nothing here is a constant; quoting one as if it were is the
  mistake this section exists to prevent. Measured at M151:

  | | `default` | `wide` |
  |---|---:|---:|
  | Files read, of the 1,039 that could declare | 42 (4%) | **1,039 (100%)** |
  | Facts | 24,871 | 36,089 |
  | `base::Feature` | 2,062 | 3,951 |
  | Feature params | 862 | 1,623 |
  | Preference keys | 689 | 2,404 |
  | Command-line switches | 288 | 1,111 |
  | Mojo interfaces | 338 | 1,455 |
  | Mojo methods | 1,362 | 5,738 |
  | WebUI controls | 884 | 1,421 |

  `default` reads 4% of the files but more than half the feature declarations,
  because curation picked the large ones. `wide` fetches about 315 MB per
  version against 40 and keeps 94 MB, since the archives are filtered as they
  unpack, and it reads every file in the tree that matches a declaration
  convention.

  Read the coverage line the run printed and state it in the report. On either
  set, `must fix: 0` never means "nothing changed" -- `default` still leaves
  two thirds of the Mojo surface and a third of the flags unread.

  **Mojo is the reason to consider `wide` for anything that matters.** It
  carries the highest-severity findings the tool produces, breaks at runtime
  rather than at build, and `default` sees 338 of 1,455 interfaces.

  **Preference keys need care whichever set you ran.** Chromium is splitting
  `chrome/common/pref_names.h` apart -- 4,322 lines at M143, 3,267 at M151 --
  and the keys land in per-component files. `default` reads only that one file,
  so a key moving out of it is indistinguishable from a key being deleted.
  `wide` reads them all, and string constants are read even under ChromeOS
  trees precisely so a move reads as a move: measured M148 → M151, of 141 keys
  that vanished on the old scope, 100 had simply moved into a ChromeOS file.

  That is what `pref_left_scan` describes, and why it scores 35 rather than as
  a confirmed removal. **Never report one as a deletion without searching the
  current tree for the key string first** -- found elsewhere means it moved and
  there is nothing to do; genuinely absent means every existing user's stored
  value is orphaned.
- **The extensions API.** Three languages share the `.idl` extension in this
  tree, and the reader understands one of them, so it reads only Blink's own
  (`third_party/blink/renderer/`). Chrome Extensions IDL and MIDL are not
  covered at all -- deliberately, after they produced 1,081 facts at M151 that
  were labelled as Web API changes and were not.
- **Page behaviour.** Only the declarative parts of a WebUI surface are read:
  the route table and the HTML templates. Logic in the accompanying TypeScript
  is not, and neither is `page_visibility.ts`.
- **Why a fork diverged.** `--mode fork` and `provenance` report *that* our
  declaration differs from upstream's and how far back the match goes. Neither
  can say whether someone chose it. A commit message, a bug id or an owner
  settles that, and none of them are in the data.
- **Implementation behind a vendor guard.** Shadow analysis finds *which*
  declarations a `SBROWSER_*` flag covers, not what our branch does differently.
- **Anything outside the repository**: server-side Finch configs, launch
  scripts, test automation, store metadata.
- **Rendered UI.** No screenshots, no layout, no visual regressions.

## Comparison methods

Use flags plus declarations to *discover*, targeted code reading to *explain*,
screenshots only to *confirm* a short list. Screenshot comparison is the
slowest and most brittle method and cannot say why something changed; using it
to discover changes is the most common mistake.
