---
name: analyzing-chromium-uprevs
description: Compares two Chromium versions - feature flags, web APIs, prefs, switches, Mojo interfaces, settings surface - separating real behaviour changes from cleanup, and produces a ranked report of what moved. Use when planning or reviewing a Chromium uprev such as M148 to M151, when asked what is new, removed, or changed between two Chromium milestones, when asked whether a Chromium change breaks anything, when interpreting a raw Chromium diff, or when deciding what work a rebase requires.
---

# Analyzing Chromium uprevs

Compare two Chromium versions and report what actually moved, separated from
what only looks like it moved.

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
2. Did only **code** change? → cleanup; matters only to something outside the
   binary that names the symbol

These are two lists with different owners and urgency. Keep them separate.

## Workflow

Copy this checklist and track progress:

```
- [ ] 1. Confirm platform and exact versions
- [ ] 2. Run chromedrift
- [ ] 3. Read Breaking, then Behaviour change
- [ ] 4. Classify each finding (decision procedure below)
- [ ] 5. Write the report, including limits
```

### Step 1: Confirm inputs

Ask for anything missing.

- **Platform** is fixed to Windows and is not a question. There is no
  `--platform` flag: Chromium wraps defaults in `#if BUILDFLAG(IS_WIN)`, so
  reading the wrong platform inverts conclusions rather than blurring them, and
  an option nobody checks is a way to be silently wrong. Read
  `platform_state.windows`, never `default_state`.
- **Exact versions**, never bare milestone numbers. `151` resolves to whatever
  is newest stable today and drifts between runs. Real example:
  `ServiceWorkerAutoPreload` is ENABLED in 143.0.7499.40 and DISABLED in
  143.0.7499.194 — same milestone, different patch release.
- **How much of the tree to read**, because it changes the answer rather than
  just the runtime — see the `--target-set` table below. If the question is
  "can we ship this uprev", the answer is `wide`.

### Step 2: Run

```bash
python3 -m chromedrift check          # verify machine, network, cache

python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151
```

Pure Python 3.9+ stdlib, no install, no Chromium checkout (pulls ~40 MB of
declaration files per version). Cold run about 97 seconds per version, so
roughly three and a half minutes for a pair; a cached run is half a second.

Outputs: `report.md` (paste into a ticket), `report.html` (filterable, fully
self-contained), `report.json` (scripting). Every finding cites `path:line` on
each side, under `change.locations` in the JSON — quote it, do not paraphrase
the file name.

**The tool does not judge.** It stops at extracted evidence and a deterministic
rank; deciding what a change means for a particular product is your job, and
this skill is the procedure for it. It knows nothing about what anyone patches,
ships or overrides — a **Breaking** row says a contract moved, not that anyone
had signed it.

Options: `--no-enrich` skips network lookups, and `--target-set` chooses how
much is read:

| | Per version | Files read | Use for |
|---|---:|---:|---|
| `minimal` | ~1 MB | 3 | smoke test |
| `default` | ~40 MB | 5% of files, over half the flags | day to day |
| `wide` | 337 MB fetched, 110 MB kept | **100% of files** | a release gate |

**Every run prints the coverage it achieved**, measured against a listing of
that version's own tree rather than assumed:

```
coverage: reads 64 of 1164 files in this tree that could declare (5% of files)
  largest gaps: chrome/browser/ (251 files), components/enterprise/ (50 files)
```

The denominator is the tree, not the roots the fetch list happens to live under.
It used to be the latter, which let `wide` grade itself 100% while 153 files the
same rule admits — `base/base_switches.h`, `cc/base/features.cc`,
`device/fido/public/features.cc` among them — sat outside the measurement
entirely. That gap is now closed — `base/`, `device/`, `cc/`, `sandbox/`,
`storage/` and the rest are fetched — so **`wide` reads 100% and the figure
means it.** Quote the number the run printed, never one from here.

**Coverage also changes the answer, not just the confidence.** A removal is an
inference from absence, so on a partial read it loses 15 points, and a
`pref_left_scan` is filed as Housekeeping rather than Breaking. Measured on the
same pair: `default` produces 139 of those in Housekeeping at 20 points, `wide`
produces 171 in Breaking at 35. **`Breaking: 0` on a default run is not a clean
bill of health.**

**The run can refuse, and both refusals mean the same thing.** `cannot diff
snapshots built from different target sets` and `cannot diff: X holds N facts
against Y's M` both say one side read a fraction of the other, so every fact
only the fuller side has would be reported as something the other removed.
Neither is a bug to work around: check the `--local-src` / `--from-src` /
`--to-src` path points at a full Chromium `src/`. Two real versions differ by
about 3%.

`report.json` carries `meta.missing_targets`, a list per side of the files the
target set asked for that the source did not have. Read it alongside the
coverage line: coverage says how much of the tree was in scope, this says what
was in scope and not there.

The same measurement is in `report.json` under `meta.coverage`, as
`{from, to}` — one per side, each with `candidates`, `read`, `missed` and
`missed_by_directory` — with up to 400 unread paths from the TO side under
`meta.uncovered_files`. It is also the last block of `report.md`, under *How
this was produced*.

`--partition settings` (repeatable: `downloads`, `bookmarks`, `history`,
`extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`,
`media`) limits what is fetched and scanned. Measured at M151 on the default
set: full run 24,966 facts, `--partition settings` 4,708. A partitioned run
prints its own coverage line, scoped to the partition's roots. **Faster and less
complete, one-directionally** — Chromium is not organized by product, so a
change affecting downloads can live in `content/` or in a Mojo interface and
match no partition. Right while iterating on one surface, wrong as a release
gate.

Other commands: `chromedrift report <report.json> --format both` re-renders
without re-running anything; `chromedrift catalog <ref>` measures what the
target set is *missing* rather than guessing.

### Step 3: Read the buckets in order

Read **Breaking**, then **Behaviour change**, then **New surface**. Skip
**Housekeeping** — with one exception. Filter it to `flag_expiring` before you
close the report: those rows are chrome://flags entries Chromium has scheduled
for deletion in the next milestone or two, so they are the only thing in the
report about work that has not happened yet. 57 of them at M148 → M151.

The bucket comes from *what happened*, not from severity, and it is decided by
the same signal that set the score — so a row is filed under the sentence it was
ranked by.

| Bucket | Means |
|---|---|
| Breaking | Something outside the binary stops working, silently: stored user data, launch scripts, Finch configs, live websites, the other process |
| Behaviour change | The Windows build behaves differently. Someone can see a difference |
| New surface | Surface that did not exist before. Nothing is switched on by it on its own |
| Housekeeping | Chromium tidying up after itself, and scheduling. Nothing observable moved, or the tool cannot tell that anything did |

**Retired flags are Housekeeping and that is deliberate.** At M148 → M151, 90
`base::Feature` flags are removed, split exactly 45 that shipped and 45 that were
abandoned, and not one changes what a user sees. If you find yourself reporting
one as a lost feature, re-read *Known traps*.

Before reading rows, read **What happened**. Both reports group every finding
under the signal that set its severity, so a 2,800-row report is about forty
things — *Now ON by default on Windows* (77), *Mojo method signature changed
(ABI)* (40), *Preference no longer in the file we read* (139). Each is a
partition, not a highlight reel: every finding appears under exactly one, so the
counts are the report. That tells you what the milestone did before you have
read a single identifier.

`report.md` groups these under the three consequence groups — behaviour
switches, external contracts, UI and scheduling — so the two thirds of a report
that is *not* about features being turned on or off is visible as its own set,
and it carries a per-screen section for the `chrome://` surfaces.

`report.html` is one sortable table instead, and carries the same sentence per
row in its **What happened** column. Sort or filter on it to get the same
grouping. Its **Where** column is the per-screen answer, one row at a time:
`settings › privacy_page` for a control, the declaring directory for everything
else.

**Two numbers, and the gap between them is information.** Severity is what this
kind of change costs; score is that after the two run-dependent deductions
(not in the Windows build on either side → 0; unconfirmed removal → −15).
Nothing raises a score, so a score below its severity always has a sentence in
`reasons` saying why. Quote that sentence rather than the number.

### Step 4: Classify each finding

Stop at the first question that settles it.

1. **Did the flag state change on our platform?** Check `platform_state` in the
   finding. `disabled → enabled` or the reverse is a real behavioural change.
   Report and stop.
2. **Did the flag disappear?** Check the state it held *before*. Signals
   `flag_retired_on` / `flag_retired_off` mean behaviour did not change here.
   The only remaining question is whether anything outside the binary was
   setting it.
3. **Is it a rename?** `feature_string_renamed`, `pref_renamed`,
   `switch_renamed`, `param_removed` compile fine and fail silently in the
   field. Always actionable if the old name appears anywhere, including
   server-side Finch configs, launch scripts and test automation, which the tool
   cannot see.
4. **Is the disappearance confirmed?** `pref_left_scan` / `switch_left_scan`
   mean "not in the files this run read". On a `default` run that is weak: of
   141 keys that vanished at M148 → M151, 100 had simply moved. Search the
   current tree for the key string, or re-run `wide`, before reporting either
   outcome.
5. Otherwise it is churn. Record, do not escalate.

Signal meanings: **see [reference/signals.md](reference/signals.md)**.

### Step 5: Report

Structure, in this order:

1. **Verdict** — one sentence on the risk of this uprev
2. **Behavioural changes** — flag state actually moved on our platform
3. **Contract breaks** — renames, removed Mojo methods, removed web APIs
4. **Silent breaks** — the ones that compile cleanly and fail in the field
5. **New capability** — what could be adopted; product input, not a blocker
6. **Limits** — what was not examined, starting with the coverage figure

Always state the exact versions compared, the target set, and which partitions
were scanned if the run was partitioned.

Every finding needs three parts: **what moved**, **whether users see a
difference**, **what someone must do**. The middle part decides priority and a
raw diff cannot supply it.

Bad: *"`LocalNetworkAccessChecksSplitPermissions` was removed in M151."*

Good: *"Local Network Access moved to split permissions. The flag was already
ENABLED at M148, so users saw this before our current base; M151 only retires
the flag. No behavioural change. Action: update any reference to
`kLocalNetworkAccessChecksSplitPermissions` or the `/localNetworkAccess`
route."*

The report carries evidence, not conclusions. Every finding shows its score
reasoning and its declaring line precisely so a conclusion can be argued with —
cite those fields rather than restating the score.

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

## Scoping to settings

Desktop settings are a WebUI page built from TypeScript and HTML templates.
Sources, the three-hop chain from a settings page to the flag behind it, and how
to size a "feature" (control / page / capability):
**see [reference/settings-surface.md](reference/settings-surface.md)**.

## What the tool cannot see

State these limits in every report. A clean report does not imply a clean uprev.

- **Whether any of it touches a particular product.** The tool compares
  Chromium against Chromium. Searching your own tree for the identifier a
  finding cites is the step that answers "does this affect us", and it is
  deliberately not automated: doing it needs a description of your codebase
  that the tool cannot obtain honestly.
- **Implementation-only changes.** The tool reads declarations (macros, IDL,
  mojom, string constants, JSON/JSON5 manifests). Behaviour changed entirely
  inside a function body is invisible.
- **Coverage depends on which target set was run, and every run prints its
  own number.** Nothing here is a constant; quoting one as if it were is the
  mistake this section exists to prevent. Measured at M151:

  | | `default` | `wide` |
  |---|---:|---:|
  | Files read, of the 1,164 that could declare | 64 (5%) | **1,164 (100%)** |
  | Facts | 24,966 | 36,832 |
  | `base::Feature` | 2,069 | 4,243 |
  | Feature params | 863 | 1,686 |
  | Preference keys | 689 | 2,460 |
  | Command-line switches | 288 | 1,222 |
  | Mojo interfaces | 338 | 1,501 |
  | Mojo methods | 1,362 | 5,903 |
  | WebUI controls | 971 | 1,431 |

  `default` reads 5% of the files but more than half the feature declarations,
  because curation picked the large ones. `wide` fetches about 337 MB per
  version against 40 and keeps 110 MB, since the archives are filtered as they
  unpack, and it reads every file in the tree that matches a declaration
  convention.

  Read the coverage line the run printed and state it in the report. On the
  default set, `default` still leaves two thirds of the Mojo surface and a
  third of the flags unread.

  **Mojo is the reason to consider `wide` for anything that matters.** It
  carries the highest-severity findings the tool produces, breaks at runtime
  rather than at build, and `default` sees 338 of 1,501 interfaces.

  **Preference keys need care whichever set you ran.** Chromium is splitting
  `chrome/common/pref_names.h` apart — 4,322 lines at M143, 3,267 at M151 —
  and the keys land in per-component files. `default` reads only that one file,
  so a key moving out of it is indistinguishable from a key being deleted.
  `wide` reads them all, and string constants are read even under ChromeOS
  trees precisely so a move reads as a move: measured M148 → M151, of 141 keys
  that vanished on the old scope, 100 had simply moved into a ChromeOS file.
- **The extensions API.** Three languages share the `.idl` extension in this
  tree, and the reader understands one of them, so it reads only Blink's own
  (`third_party/blink/renderer/`). Chrome Extensions IDL and MIDL are not
  covered at all — deliberately, after they produced 1,081 facts at M151 that
  were labelled as Web API changes and were not.
- **Mojo structs, enums and unions.** The extractor reads `interface`
  declarations only, which is about three quarters of the Mojo declaration
  surface at M151.
- **Page behaviour.** Only the declarative parts of a WebUI surface are read:
  the route table and the HTML templates. Logic in the accompanying TypeScript
  is not, and neither is `page_visibility.ts`.
- **Anything outside the repository**: server-side Finch configs, launch
  scripts, test automation, store metadata.
- **Rendered UI.** No screenshots, no layout, no visual regressions.

## Comparison methods

Use flags plus declarations to *discover*, targeted code reading to *explain*,
screenshots only to *confirm* a short list. Screenshot comparison is the
slowest and most brittle method and cannot say why something changed; using it
to discover changes is the most common mistake.
