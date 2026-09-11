# Confirm scope and select evidence

The agent MUST establish what the user needs before analyzing the comparison.
Product areas and declaration kinds are different: a Settings change can
involve a route, preference, C++ feature, IPC interface and unparsed code.
A kind selection is a starting point, not proof that other kinds cannot matter.

## Ask and record the answer

Ask for areas and the decision the report should support. Allow several
areas, free-text areas and a broad comparison. Do not restrict discovery to
the examples in SKILL.md. If the user does not know the technical kinds,
proceed with their product-language answer; do not ask them to classify code.

For a downstream Chromium product, ask for relevant patches, components or
configuration when needed to decide product-specific impact. Unknown product
details remain unknown; do not guess which consumers the product ships.
The tool evaluates Windows conditions, not arbitrary platforms.

An explicit answer already in the task is sufficient. Otherwise MUST wait
for the answer. A selected UI default, silence or a previous unrelated review
does not confirm the scope. The user may explicitly delegate the scope choice;
then state the chosen scope before proceeding.

After creating or opening the review, save `request.md` in that directory
using the environment's file-editing mechanism. Record:

- the user's actual scope answer and requested versions; add resolved refs
  and the evidence fingerprint the tool returns once available;
- selected areas, requested decisions and optional kind preferences;
- explicit exclusions, if any; distinguish exclusions from lower priorities;
- known product/build context and missing information;
- the report/cache/Git paths used and any agreed acquisition restrictions;
- resource limits actually known, and whether continuation in a fresh context
  is available. Do not invent an exact token allowance or total work budget.

This note preserves the request; the CLI does not interpret it as an automatic
filter or verify that the user really approved it. MUST keep it consistent
with the conversation. On a scope change, revisit exclusions and earlier
conclusions that depend on the old scope. Do not mix reviews with different
scope and present their completeness counts as equivalent.

## Choose acquisition separately from analysis

For a new comparison, explain the tradeoff before choosing the acquisition:

- The full scan retains the most possible cross-area evidence, and still does
  not cover all Chromium code or syntax. `--target-set smoke` reads three
  files to check the tool runs; it cannot answer a comparison question.
- `--partition` reduces acquisition to supported paths for the chosen areas.
  It is not a complete boundary for their behaviour, and coverage is still
  measured against the whole tree, so a removal of a kind it reads only
  inside its own roots is `unconfirmed`. Use it only after the
  user accepts that narrower acquisition. Confirm available options with
  `python3 -m chromiumdiff run --help`; do not invent a partition for an area
  not supported by the CLI.
- An existing broad report can be queried without downloading or placing the
  entire report in context. Do not rebuild it merely to focus on one area.

A source change outside `settings/` can affect Settings. Follow referenced
conditions, consumers, shared storage and relevant history across directory
boundaries. Fetch exact-ref missing files when permitted; otherwise report
the missing evidence. A user-selected kind MUST NOT exclude supporting source
or related kinds needed to explain its behaviour.

## Read whole-index summaries before individual items

After `review init`, MUST execute these commands and read the results:

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 3
```

`check` exits 1 for unfinished work; this is expected initially. `overview`
aggregates the complete saved index in the tool's own process. It does not emit
raw findings, diff bodies or per-item IDs. `index_total` is the unfiltered
inventory size; `total` is the number of summary groups in that query.
Page through the groups with `--cursor` until `next_cursor` is null. Path
groups can overlap when a finding has several paths. Counts are not events,
importance, token estimates or evidence that the items have been reviewed.

Use `--path-prefix` to examine a smaller observed directory and increase
`--path-depth` for more detail. Prefix matching uses whole path components,
not a feature-name dictionary. Use values from actual output, for example:

```bash
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 5 --path-prefix chrome/browser/resources
python3 -m chromiumdiff review index out/upgrade/review --status pending --path-prefix chrome/browser/resources/settings --limit 20
python3 -m chromiumdiff review index out/upgrade/review --status pending --fact-kind pref --limit 20
python3 -m chromiumdiff review index out/upgrade/review --status pending --item-kind source_delta --limit 20
```

`--fact-kind` accepts declaration kinds in groups with `item_kinds.finding`.
For `source_delta` or `milestone_lead`, use `--item-kind` instead. Repeating it
selects any listed kind. Repeated `--path-prefix` values likewise mean any
listed prefix; different filters are combined. A fact-kind filter returns
findings only, so it MUST be accompanied by source-delta investigation where
relevant. A path prefix can only match an item that has a path, so it excludes
every item that has none -- every `milestone_lead` -- however complete the
sweep looks; `path_filter` in the result counts those by kind, and
`--item-kind milestone_lead` without a prefix is how to read them. Paths and
kind filters select retrieval, not event membership or out-of-scope decisions.
They do not modify the index or clear pending items.

## Spend context on the user's questions

For a selected product area, MUST use [focus.md](focus.md) to build and inspect
a source-backed candidate packet. Path/kind queries alone miss dependencies
declared elsewhere, including Mojo used by unchanged consumer files.

Use the summaries to identify evidence for the confirmed areas, then inspect
related declarations, before/after source and consumers. Querying an area
does not require listing every unrelated row first. Within that area, explain
concrete transitions and actions, not a fixed number of high-scoring entries.
Importance must be justified by the requested decision and supported effect,
not the number of changed lines, a familiar feature name or a bucket.

Keep unrelated, excluded and uncertain scope distinguishable. A path outside
the initial query is not automatically unrelated. When relevance is unclear,
retain a question or a scope limit instead of silently discarding the item.
Account for source-only changes and milestone leads as well as findings.

Pagination bounds one response, not the accumulated context. MUST NOT claim
that reading every page fits within 200k tokens. Save the analysis and source
locations, and resume in a fresh context when the runner supports it. With a
single fixed context and no continuation, narrow the work with the user or
report the remaining scope explicitly. Summary counts do not establish that
all important changes have been found.

## Before delivery

MUST check that the recorded request matches the user's choice, required
references were read, and the `chromiumdiff` commands actually ran. Include paths to
the saved review and request, exact refs, final check results and remaining
limits. Do not write that a reference was read or a command passed without
having done so. If the runner exposes execution logs, preserve them for audit.

`review check` validates accounting, not reference-reading or user consent.
`MUST` instructions cannot force a runner that ignores the skill to execute
tools. Enforcing those actions outside the agent requires the caller to check
actual tool execution and refuse an unsupported completion claim; a manually
checked box is not equivalent to that evidence.

After retrieving and checking the scope inventory, record its decision items
using [selection.md](selection.md). That gives the selection its own accounting
alongside the whole-index accounting, without treating a retrieval filter as
proof of completeness.
