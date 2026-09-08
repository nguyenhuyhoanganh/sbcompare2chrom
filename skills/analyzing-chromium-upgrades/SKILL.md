---
name: analyzing-chromium-upgrades
description: Ask which Chromium areas and decisions matter, then compare versions using the chromiumdiff scripts, required references and versioned evidence. Use for Chromium upgrade analysis and report interpretation, with impact, actions and explicit coverage limits.
---

# Analyzing Chromium upgrades

Explain what changed between two Chromium versions, how the changes relate,
and what the user should verify or update. The script extracts declarations
and compares them. The agent determines the meaning of those differences.
Do not use buckets, scores, signals or clusters as final conclusions.

## Required steps before analysis

`MUST` marks a required step, not a suggestion. These requirements apply to
upgrade analysis, not merely explaining what a command does.

1. **MUST establish the user's scope before running a comparison or analyzing
   findings.** Ask which areas matter and what decisions the report should
   support. Offer Settings, History, Bookmarks, Extensions, Downloads, another
   user-named area, or a broad review. Multiple areas are allowed; this is not
   a fixed discovery list. Offer technical declaration kinds only as an
   optional refinement. Do not require the user to know parser terminology.
2. **MUST wait for the user's choice when it is missing.** Do not silently
   choose `wide`, all areas, a top-N sample or the highest scores. If the user
   already supplied explicit scope and priorities, use those answers without
   asking again. On resume, keep the recorded scope unless the user changes it.
3. **MUST read the required references below before their corresponding work.**
   Read each selected reference completely, not just its heading or search
   matches. A reference already read in this run need not be loaded again.
4. **MUST execute the documented scripts and inspect their actual results.**
   Reading SKILL.md, copying example commands or reading only `report.md` does
   not complete an analysis. If a required script or reference is unavailable,
   state the blocker and do not claim the dependent work is complete.

A short opening question, adapted to the user's language:

> Which areas should I review: Settings, History, Bookmarks, Extensions,
> Downloads, other areas you name, or a broad comparison? What matters most:
> changes users will notice, new capabilities, or changes your product must
> adapt to? You can select several and describe your own priorities.

Ask for missing versions in the same exchange. See
[reference/scoping.md](reference/scoping.md) for recording the answers,
choosing acquisition scope and using bounded queries without omitting dependencies.

| Before this work | Reference that MUST be read |
|---|---|
| Choosing acquisition/query scope or starting detailed analysis | [scoping.md](reference/scoping.md) |
| Building or reading evidence for a selected product area | [focus.md](reference/focus.md) |
| Starting or resuming a review, saving decisions or refreshing inputs | [investigation.md](reference/investigation.md) |
| Drawing conclusions from source, availability or absence | [traps.md](reference/traps.md) |
| Interpreting classifier signals, buckets or scores | [signals.md](reference/signals.md) |
| Analyzing WebUI controls, routes, preferences or visibility | [settings-screen.md](reference/settings-screen.md) |
| Looking up CLs/bugs or claiming cause, intent, split, revert or merge | [history.md](reference/history.md) |

The scripts MUST be used at these stages:

- New comparison: `check`, `run`, then `review init` using the chosen inputs.
- Existing report: `review init` only if no review exists; do not regenerate
  an unchanged report. Then run `review check` and `review overview`.
- Evidence analysis: use `review index`, `inspect`, `related` and `source`
  as needed to inspect findings and exact-version source. A keyword search
  alone MUST NOT be treated as evidence of behaviour or complete coverage.
- Saving and delivery: `review record`, `review check`, then `review render
  --require-complete` for completed accounting. A partial report MUST retain
  its status and unfinished counts. Do not bypass a failed check by changing
  unexplained items to `explained` or `out_of_scope`.

Use these terms consistently:

- **Fact**: a declaration extracted from one version; it may be unchanged.
- **Finding**: a difference between extracted facts, identified by `kind:key`.
- **Source delta**: a difference in file contents, including code the parser
  does not understand. A **hunk** is one section of a file diff.
- **Event**: one related change explained in the final report. It may involve
  several findings, files and commits, or just one finding.
- **Consumer**: code or an external system that calls an API, reads a value,
  implements an interface or otherwise depends on the changed behaviour.
- **Gate**: a condition controlling whether code or an API is available.
  **Rollout** means actual availability in a deployed product, which can
  differ from the default declared in source.

## Start or resume the comparison

Use the confirmed scope and versions. An unanswered scope question is not
permission to start. A broad review includes new capabilities, behaviour
changes, API changes, migrations and scheduled work; do not restrict it to
compatibility problems. Keep the user's answers in `review/request.md` as
described in `reference/scoping.md`.

Run commands from the project root. Python 3.9+ standard library is sufficient.
The script compares Windows conditions; there is no platform CLI option.
Record the exact `from_ref` and `to_ref` returned in the report. Bare milestone
numbers can resolve differently on later runs.

For a new comparison after scope confirmation (broad acquisition shown):

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --target-set wide --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Replace FROM/TO and the output paths with the requested comparison. `wide`
scans more supported files than `default`; it does not cover all Chromium
code or syntax. `minimal` is for basic checks. `--partition` restricts scope.

For an existing report without a review, run `review init` with its actual
cache. For an existing review, resume with `index`, `events` and `check`;
do not initialize it again unless its inputs changed.

A local Chromium Git repository can provide a list of all changed paths at
the two refs: add `--source-repo /path/to/chromium/src` to the initial
`review init`. The command reads Git objects without changing the checkout.
Without Git, source comparison covers cached files only. A missing cached
file means its contents are unknown, not that Chromium removed it.

Read [reference/investigation.md](reference/investigation.md) before recording
decisions or refreshing an existing review. It explains how to read the saved
configuration, preserve the cache/Git source and save progress.

## Read the reports and source

- `report.md` gives an overview. Its displayed tables may be incomplete.
- `report.json` contains all findings. Use structured queries; do not load
  the whole file into context or treat a text search as a complete review.
- `review-index.json` contains the input configuration, findings, unchanged
  facts, declared relationships and source deltas.
- `review.json` stores events, supporting evidence and decisions about every
  indexed item. `review.md` is the report rendered from those decisions.

A finding's `change` contains `before`, `after`, `deltas`, `paths`,
`locations` and `signals`. `unconfirmed` indicates insufficient evidence for
absence. Read the coverage and reasons before calling a declaration removed.

## Analyze the changes

1. Read the comparison metadata and run `review overview` before detailed
   queries. Use its whole-index counts to choose queries for the confirmed
   scope; do not load thousands of raw rows into context. Account for the
   inventory, including low scores, no-signal findings, source deltas and
   milestone summaries. An exclusion needs a reason tied to the user's scope,
   not merely a failed keyword or path match. Follow `reference/scoping.md`.
2. Identify possible related changes. Use `related` to examine declared
   relationships on both versions, including declarations that did not change.
   A shared flag, prefix, screen, interface or CL is a reason to investigate,
   not proof that the items form one event.
   For an area-focused comparison, MUST use the procedure in
   [reference/focus.md](reference/focus.md) to retrieve source-backed
   candidates before treating a path filter as the full evidence set.
3. Read before/after source and relevant consumers. Inspect all changed hunks
   of files in the confirmed scope, even when some hunks already have findings.
   For shared dependency files, follow the referenced sections and related
   hunks as described in `reference/focus.md`; do not mark the entire file
   reviewed if other hunks remain unread. Follow identifiers the graph could
   not resolve. Changes without a finding still need analysis.
4. When cause, sequence or intent is unclear, use
   [reference/history.md](reference/history.md). It covers both finding-based
   lookup and direct file history when `why.py` cannot find a row. Verify
   milestone summaries against the exact comparison; their dates alone do
   not establish availability in either version.
5. Group items only when their evidence supports one related change. Explain
   what each item contributes. Separate unrelated changes even if the tool
   groups them. State source observations separately from inferred intent
   and product-specific consequences.
6. After each batch, save events and unanswered questions. Read the saved
   event list and compare new evidence with earlier decisions. Revise groups
   when evidence shows that they should be combined or separated.
7. Before delivery, check pending items, unresolved questions and provisional
   events. Run `review check` and `review render --require-complete`. If work
   remains and permitted checks are still available, continue the next batch.
   If an actual resource limit or missing evidence prevents completion, save
   progress and deliver a partial report with counts and the next checks.

Apply this procedure to unfamiliar identifiers too. Reference examples and
signal names are not a list of features to discover. Scores may affect work
order, but must not decide which evidence is examined or which events exist.
Do not set a fixed number of events to find. A small batch limits what is in
context at once, not how much of the comparison to review. Follow the repeatable
pending-item procedure in `reference/investigation.md`; do not stop after the
first page or a selection of interesting examples.

## Query in small sections

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
python3 -m chromiumdiff review events out/upgrade/review --limit 30
python3 -m chromiumdiff review inspect out/upgrade/review 'KIND:KEY'
python3 -m chromiumdiff review related out/upgrade/review 'KIND:KEY' --hops 2
python3 -m chromiumdiff review unresolved out/upgrade/review
python3 -m chromiumdiff review source out/upgrade/review path/to/file.cc --side diff --start 1 --end 120
```

Use IDs and paths from the actual index. All queries support `--cursor`,
`--limit` and `--max-chars`. The output limit is characters, not model tokens.
Read remaining pages until `next_cursor` is null. For `index`, use
`--after NEXT_AFTER` if decisions change between pages: numeric offsets on
a shrinking `--status pending` list can skip items.
Alternatively, decide every item returned in the current pending batch, save
it, then repeat `index --status pending` from cursor 0. Check the whole review
before stopping: an empty filtered search does not mean no work remains.
`review unresolved` lists unresolved graph references, not unfinished review
decisions; use `index --status unresolved` for those.

`inspect` returns fields as JSON-pointer paths. Long strings have offsets and
may span pages. `events` returns a short list; inspect an event ID to read its
full saved analysis without loading the complete review.

`related` returns chains of typed references, not causal conclusions. It does
not automatically expand ambiguous references or weak CL matches. If a node
has too many links, query that node with `--hops 1` and read its pages.

`source` returns exact refs, source origins and SHA-256 hashes. Its `next_line`
is separate from `next_cursor`: finish pages for the requested line range,
then advance to the next range. Use `--side from` or `--side to` for source
line numbers; diff line numbers are not source line numbers.

For a missing file, `source --fetch` retrieves the requested path at the exact
ref. If retrieval fails or is unavailable, state the missing evidence. Do not
substitute a file from another cached version. To locate consumers in cached
source, read the exact `inputs.source_roots` from the index, then use:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Set the identifier and root to observed values. Search results are locations
to inspect, not proof of execution. In Git mode, use the exact-ref `git grep`
procedure in `reference/history.md`; the working checkout may be different.

## Interpret the evidence

- Flags and APIs: compare the recorded Windows state and all relevant build
  and runtime conditions. A source default is not measured product rollout.
- Removed declarations: inspect replacement declarations and consumers before
  concluding that the capability was removed.
- API or IPC signatures: a declaration changed. Establish affected consumers
  and version combinations before claiming a build or runtime failure.
- Prefs, switches and parameters: locate readers, writers, migrations and
  external overrides. No recorded gate does not prove unconditional use.
- Two source versions establish their net difference. Claims about a split,
  revert or later merge require the corresponding history.

Read [reference/signals.md](reference/signals.md) to interpret classifier
labels, [reference/traps.md](reference/traps.md) for common limits of source
evidence, and [reference/settings-screen.md](reference/settings-screen.md)
when tracing WebUI routes, controls and visibility conditions.

## Write the final report

Use one numbered item per event, titled with the change rather than its
bucket, score or identifier alone. Explain before/after, the reason for
grouping, affected consumers, conditions, evidence, action and uncertainty.
Use direct sentences and define unfamiliar technical terms. Write in the
user's language; preserve source identifiers and command names exactly.

Include exact versions, platform and scope. Distinguish changes established
by source from consequences that depend on the user's build or configuration.
Include a short summary and links to the full review when it is long.
The full review must retain every supported event, even if the summary shows
only a few. Report `check.total`, decision counts, `by_kind` and provisional
event count; finding and file counts overlap and are not event counts.
Do not call unexamined items `explained` or `out_of_scope` to finish sooner.

Accounting for every indexed item does not prove that every meaningful change
was discovered. Cached source may be incomplete; parsers cover selected
syntax. External configuration, product patches and rendered UI need separate
evidence. Do not present `review check` as release approval.
