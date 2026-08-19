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
self-contained), `report.json` (scripting).

**The tool does not judge.** It stops at extracted evidence and a deterministic
rank; deciding what a change means for the product is your job, and this skill
is the procedure for it. Nothing in the report is a verdict, so there is no
verdict column to mistake for a clean result — but equally, an empty **Must
fix** means "no evidence was supplied", never "nothing to do".

Options: `--no-enrich` skip network lookups, `--target-set minimal` fast smoke
run, `--mode fork` compare against a fork instead of across time.

`--partition settings` (repeatable: `downloads`, `bookmarks`, `history`,
`extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`,
`media`) limits what is fetched and scanned. Measured: full run ~120 s and
24,646 facts, `--partition settings` 24 s and 4,467. **Faster and less
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
- **Roughly 40% of feature flags.** This is the largest limit and it is
  measured, not estimated by feel. At M151 the tool captures 2,062
  `base::Feature` declarations. Sampling the files it does not fetch puts about
  **1,200 more** in files whose names follow the convention, plus about **130**
  in files that follow no convention at all — so coverage of the flag surface is
  near **60%**, and `must fix: 0` never means "nothing changed".
  Run `chromedrift catalog <ref>` for the current number and the missing paths
  by name; closing a gap is one line in `targets.py`.

  Per source type, measured at M151:

  | Source | Covered | In tree |
  |---|---:|---:|
  | Blink runtime features | 1 file | 1 file (complete) |
  | Web IDL | 2,167 | 2,575 (84%) |
  | Mojo interfaces | 490 | 1,588 (**30%**) |
  | `pref_names` files | 3 | 164 (**1%**) |
  | WebUI surfaces | 8 | 132 (**6%**) |

  Mojo and prefs are the ones to state explicitly in a report: Mojo carries the
  highest-severity findings, and prefs outside `chrome/common/pref_names.h`
  — every `components/*/pref_names.h` — are simply not read.
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
