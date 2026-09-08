---
name: analyzing-chromium-upgrades
description: Compares two Chromium versions with the chromiumdiff scripts and explains what changed, what it affects and what to verify or update, scoped to the product areas the user names. Use when analyzing a Chromium upgrade or version bump, interpreting a chromiumdiff report.json or review directory, or reviewing one area such as Settings, WebUI, Mojo or feature flags across two milestones. Use investigating-chromium-root-causes instead to trace one identifier or one reported symptom back to its cause.
---

# Analyzing Chromium upgrades

The script extracts declarations and compares them. The agent determines what
those differences mean, what they affect and what the user must verify or
update. Buckets, scores, signals and clusters are work order, never a
conclusion.

## The workflow

Copy this checklist into your reply and tick each line as you finish its step:

```
Chromium upgrade review:
- [ ] 1 Confirm the scope -- read reference/scoping.md first
- [ ] 2 Build or open the comparison
- [ ] 3 Take the whole-index inventory
- [ ] 4 Retrieve evidence for the scope -- read reference/focus.md first
- [ ] 5 Read the evidence -- read reference/traps.md first
- [ ] 6 Group into events and record decisions -- read reference/investigation.md first
- [ ] 7 Repeat 4 to 6 until the scope is accounted for
- [ ] 8 Render and deliver
```

Each step ends with a **Checkpoint**: a condition, and what to do when it does
not hold. Do not start a step before the previous checkpoint holds, and do not
tick a line whose checkpoint you have not checked.

Read each named reference in full before its step; a reference already read in
this run need not be loaded again. Three more are read inside step 5 when
their subject arises: [signals.md](reference/signals.md) for classifier
labels, [settings-screen.md](reference/settings-screen.md) for WebUI routes,
controls and visibility, and [history.md](reference/history.md) for CLs, bugs
and any claim about cause, intent, split, revert or merge.

`MUST` marks a required action. Run every command from the project root;
`python3 -m chromiumdiff` fails anywhere else. Reading this file, copying an
example command or reading `report.md` alone passes no checkpoint.

## Terms

- **Fact**: a declaration extracted from one version; it may be unchanged.
  `--fact-kind` selects by its kind.
- **Finding**: a difference between extracted facts, identified by `kind:key`.
- **Source delta**: a difference in file contents, including code no parser
  understands. A **hunk** is one section of a file diff.
- **Event**: one related change explained in the final report, covering one or
  several findings, files and commits.
- **Consumer**: code or an external system that calls an API, reads a value,
  implements an interface or otherwise depends on the changed behaviour.
- **Gate**: a condition controlling whether code or an API is available.
  **Rollout** is actual availability in a deployed product, which can differ
  from the default declared in source.
- **Scope**: the areas and decisions the user confirms at step 1.
  **Acquisition** is separate: how much Chromium the script downloads and
  parses, set by `--target-set` and `--partition` at step 2.

## Step 1 — Confirm the scope

MUST establish the scope before running a comparison or analyzing findings.
Ask which areas matter and what decisions the report should support:

> Which areas should I review: Settings, History, Bookmarks, Extensions,
> Downloads, other areas you name, or a broad comparison? What matters most:
> changes users will notice, new capabilities, or changes your product must
> adapt to? You can select several and describe your own priorities.

Adapt it to the user's language and ask for missing versions in the same
exchange. Those areas are examples, not a discovery list. Offer declaration
kinds only as an optional refinement; do not make the user classify code.

MUST wait while the answer is missing. Do not choose `wide`, all areas, a
top-N sample or the highest scores instead. If the user already gave an
explicit scope and priorities, use them without asking again; on resume, keep
the recorded scope unless the user changes it.

A broad review is a valid answer, covering new capabilities, behaviour
changes, API changes, migrations and scheduled work, not only compatibility
problems.

[reference/scoping.md](reference/scoping.md) lists the fields to record in
`review/request.md` and how to choose acquisition without dropping the
dependencies a selected area needs.

**Checkpoint 1.** `review/request.md` exists and answers every field
scoping.md lists. An assumed scope fails this, and so does one you chose
yourself: stop and ask.

## Step 2 — Build or open the comparison

The Python 3.9+ standard library is sufficient; install nothing. The script
compares Windows conditions and has no platform option. Record the exact
`from_ref` and `to_ref` the report returns, because bare milestone numbers
resolve differently on a later run.

For a new comparison, with broad acquisition shown:

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --target-set wide --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Replace FROM/TO and the paths with the requested comparison. `wide` scans more
supported files than `default` and still covers neither all Chromium code nor
all syntax. `--partition` narrows acquisition to supported paths, and is used
only after the user accepts that narrower input.

For an existing report without a review, run `review init` with that report's
own cache. For an existing review, go to step 3; initialize again only if its
inputs changed, and read
[reference/investigation.md](reference/investigation.md) first, because a
refresh must carry the saved cache and Git source forward.

Adding `--source-repo /path/to/chromium/src` to `review init` supplies every
changed path at the two refs from a local Chromium Git repository, reading Git
objects without touching the checkout. Without it, source comparison covers
cached files only, and a missing cached file means unknown contents, not
removal by Chromium.

The run writes:

- `report.md`, an overview whose displayed tables may be incomplete.
- `report.json`, all findings. Query it; do not load it whole, and do not
  treat a text search over it as a review.
- `review-index.json`, the input configuration, findings, unchanged facts,
  declared relationships and source deltas.
- `review.json`, the events, evidence and decision for every indexed item.
  `review.md` is rendered from it at step 8.

**Checkpoint 2.** `review init` exited 0 and the review directory holds
`review-index.json` and `review.json`. If it failed, fix the inputs and run it
again; analyzing `report.md` on its own does not pass it.

## Step 3 — Take the whole-index inventory

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 3
```

`check` exits 1 while work remains, which is expected here; read its JSON.
`overview` aggregates the saved index inside the script process and emits
counts, never rows or diff bodies, so choose the queries for the scope from
those counts instead of paging raw rows into context.

The inventory includes low scores, no-signal findings, source deltas and
milestone summaries. An exclusion needs a reason tied to the scope, not a
failed keyword or path match. scoping.md gives the `--path-prefix`,
`--item-kind` and `--fact-kind` filters and what each one does not select.

**Checkpoint 3.** The `check` and `overview` JSON have been read,
`index_total` is known, and the queries for the scope come from those counts.
Choosing them from the tables in `report.md` does not pass it.

## Step 4 — Retrieve evidence for the scope

MUST follow [reference/focus.md](reference/focus.md) before treating a path
filter as the full evidence set. A path filter misses dependencies declared
elsewhere, including Mojo interfaces that unchanged consumer files call.

```bash
python3 -m chromiumdiff review focus out/upgrade/review \
  --path-prefix PREFIX --output out/upgrade/review/area-focus.json
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json
```

Take PREFIX from the step 3 output. focus.md covers the remaining options, the
packet sections and how to page them.

Use `review related` as well, to read declared relationships on both versions
including declarations that did not change. A shared flag, prefix, screen,
interface or CL is a reason to investigate, not proof of one event. The packet
is retrieval evidence: reading it marks nothing reviewed and excludes nothing.

**Checkpoint 4.** The packet exists and every section you selected was paged
until `next_cursor` came back null, `unresolved` included. A section stopped
mid-page is unread evidence.

## Step 5 — Read the evidence

Read [reference/traps.md](reference/traps.md) before drawing any conclusion
from source, availability or absence.

Read before/after source and the relevant consumers. Inspect every changed
hunk of a file inside the scope, even where hunks already carry findings. For
a shared dependency file outside the scope, follow the referenced declarations
and related hunks as focus.md describes, and do not mark the whole file
reviewed while other hunks are unread. Follow identifiers the graph could not
resolve. A change with no finding still needs analysis.

A finding's `change` holds `before`, `after`, `deltas`, `paths`, `locations`
and `signals`. `unconfirmed` means the evidence for absence is insufficient:
read the coverage and reasons before calling a declaration removed.

What each kind of evidence does and does not establish:

- Flags and APIs: compare the recorded Windows state and every relevant build
  and runtime condition. A source default is not measured rollout.
- Removed declarations: inspect replacement declarations and consumers before
  concluding the capability is gone.
- API or IPC signatures: a declaration changed. Establish affected consumers
  and version combinations before claiming a build or runtime failure.
- Prefs, switches and parameters: locate readers, writers, migrations and
  external overrides. No recorded gate does not prove unconditional use.
- Two source versions establish their net difference. A split, revert or later
  merge is a claim about history and needs history.

Read [signals.md](reference/signals.md) before interpreting classifier labels,
[settings-screen.md](reference/settings-screen.md) when tracing WebUI routes,
controls and visibility, and [history.md](reference/history.md) when cause,
sequence or intent is unclear. history.md covers finding-based lookup and the
direct file history to use when `why.py` finds no row. Check a milestone
summary against the exact comparison; its date establishes availability in
neither version.

Query mechanics for `index`, `inspect`, `related` and `source` are at the end
of this file.

**Checkpoint 5.** Every candidate in the batch has its before/after source
read and its conditions identified, and every item with missing evidence
carries a named next check. A preview marked `truncated` is not read evidence:
expand it with `review inspect` first.

## Step 6 — Group into events and record decisions

Read [reference/investigation.md](reference/investigation.md) first, for the
decision format, the disposition states and the pending-item procedure.

Group items only where their evidence supports one related change, and say
what each item contributes. Separate unrelated changes even when the tool
groups them. Keep source observations, inferred intent and product-specific
consequences as separate statements.

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
```

Save events and unanswered questions in each batch. Read the saved event list
and compare new evidence against earlier decisions, revising a group when the
evidence says it should be combined or separated. Batch boundaries must not
become event boundaries.

**Checkpoint 6.** `review record` accepted the batch, and the `review check`
run after it shows the pending count fall by the number of items decided. If
it did not fall, read the record result; recording a different sample instead
does not pass it.

## Step 7 — Repeat 4 to 6 until the scope is accounted for

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
```

Keep the scope's path and kind filters while continuing that query, and
inspect supporting source and dependencies outside those filters separately.
investigation.md gives the cursor rules that stop a shrinking pending list
from skipping items.

The confirmed scope is the only boundary that ends the work before the whole
index is accounted for. Interesting-looking rows, a score threshold and a page
count are not boundaries. A small batch limits what is in context at once, not
how much of the scope to review: do not stop after the first page and do not
set a target number of events. Apply the same procedure to unfamiliar
identifiers, because reference examples and signal names are not a list of
features to discover.

An empty filtered query does not mean no work remains. `review unresolved`
lists unresolved graph references, which are not unfinished decisions; use
`index --status unresolved` for those. Revisit provisional events, and recheck
pending items after an event revision or a refresh, because both can return
items to pending.

**Checkpoint 7.** `index --status pending` with the scope's filters returns no
rows, the provisional events have been revisited, and `review check` has been
read for the whole-index counts. An empty filtered query alone does not pass
it: the filter may be wrong rather than the work finished.

## Step 8 — Render and deliver

```bash
python3 -m chromiumdiff review render out/upgrade/review
```

Add `--require-complete` when the whole index was reviewed; it exits 1 without
writing `review.md` while items or events are unfinished. A scoped review
never reaches that state, because items outside its scope stay pending, so
render it without the option and keep its PARTIAL status. `render` rewrites
`review.md`, so the confirmed scope goes into the delivered summary, taken
from `review/request.md`, with the untouched counts. If a resource limit or
missing evidence stopped the work earlier, name which of the two and give the
counts and next checks. Do not clear a failed check by changing unexamined
items to `explained` or `out_of_scope`.

Write one numbered item per event, titled with the change rather than its
bucket, score or identifier. Give before and after, the reason for grouping,
affected consumers, conditions, evidence, action and uncertainty. Write in the
user's language and preserve source identifiers and command names exactly.

Include the exact versions, the platform and the confirmed scope, and separate
what source establishes from what depends on the user's build or
configuration. A long report gets a short summary and links to the full
review, which retains every supported event. Report `check.total`, the
decision counts, `by_kind` and the provisional event count; finding and file
counts overlap and are not event counts.

Accounting for every indexed item does not prove every meaningful change was
discovered: cached source may be incomplete and parsers cover selected syntax.
External configuration, product patches and rendered UI need separate
evidence. `review check` is not release approval.

**Checkpoint 8.** `review render` wrote `review.md`, and the delivered summary
names the confirmed scope, the counts and the limits. A summary that reports
events without them does not pass it.

## Query mechanics

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
python3 -m chromiumdiff review events out/upgrade/review --limit 30
python3 -m chromiumdiff review inspect out/upgrade/review 'KIND:KEY'
python3 -m chromiumdiff review related out/upgrade/review 'KIND:KEY' --hops 2
python3 -m chromiumdiff review unresolved out/upgrade/review
python3 -m chromiumdiff review source out/upgrade/review path/to/file.cc --side diff --start 1 --end 120
```

Use IDs and paths from the actual index. Every query takes `--cursor`,
`--limit` and `--max-chars`, and that limit counts characters, not tokens.
Read pages until `next_cursor` is null. For `index`, use `--after NEXT_AFTER`
when decisions change between pages, because numeric offsets on a shrinking
`--status pending` list skip items; deciding the whole returned batch and
repeating the query from cursor 0 works too.

`inspect` returns fields as JSON-pointer paths, and long strings have offsets
and may span pages. `events` returns a short list; inspect an event ID for its
full saved analysis without loading the whole review.

`related` returns chains of typed references, not causal conclusions, and does
not expand ambiguous references or weak CL matches on its own. Query a node
with too many links using `--hops 1` and read its pages.

`source` returns exact refs, origins and SHA-256 hashes. Its `next_line` is
separate from `next_cursor`: finish the pages for a line range before
advancing to the next range. Use `--side from` or `--side to` for source line
numbers, because diff line numbers are not source line numbers. For a missing
file, `source --fetch` retrieves the path at the exact ref; if that fails,
state the missing evidence rather than substituting another version's file.

A keyword search MUST NOT be treated as evidence of behaviour or of coverage.
To locate consumers in cached source, read the exact `inputs.source_roots`
from the index, then:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Search results are locations to inspect, not proof of execution. In Git mode
use the exact-ref `git grep` procedure in `reference/history.md`, because the
working checkout may differ.
