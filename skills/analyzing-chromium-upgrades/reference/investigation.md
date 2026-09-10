# Saving analysis and preserving inputs

MUST read this reference before initializing, resuming, recording or refreshing
a review. Confirm the user scope first using [scoping.md](scoping.md). An
existing report or cache does not by itself establish what the user wants.

## Read the saved configuration

Run this from the project root, replacing only the review directory. It prints
selected fields without placing the complete index in context.

```bash
python3 - out/upgrade/review <<'PY'
import json
import sys
from pathlib import Path

index = json.loads((Path(sys.argv[1]) / "review-index.json").read_text(encoding="utf-8"))
keys = ("report", "refs", "cache", "source_roots", "source_scope",
        "platform", "target_set", "partitions", "coverage")
print(json.dumps({key: index["inputs"].get(key) for key in keys}, indent=2))
print(json.dumps({"warnings": index["warnings"]}, indent=2))
PY
```

`source_scope.mode` distinguishes cached files from a Git repository.
`source_roots` identify cached trees. In Git mode, read the recorded commits
from the repository; do not assume the working checkout matches either ref.
Keep the printed cache path for `chromiumdiff why` and `chromiumdiff cl`
lookups.

## Work in small batches

MUST preserve the confirmed scope in `request.md`. Run `review overview`
before detailed queries; do not enumerate thousands of unrelated rows into
context. Keep the current questions and a short event list in context. Read
only the finding fields, related declarations and source sections needed for
those questions. Save complete decisions in `review.json` after each batch.

Every indexed item needs a decision:

- `event`: the item belongs primarily to one event. Other events can cite it
  as supporting evidence without assigning it twice.
- `explained`: inspected, but no separate event is warranted. State the
  reason and source location; a label such as "cleanup" is not an explanation.
- `out_of_scope`: excluded by the user's scope, with a specific reason.
- `unresolved`: a question still needs evidence. State the next check.

Items without a decision are `pending`. These states track analysis work;
they are not categories for the final report.

A `file:` item represents the entire file diff. For a file inside the confirmed
scope, inspect its changed hunks and record which event explains each relevant
one. For a shared file outside that scope, inspect only the hunks its findings
and references point at, then record the file as `out_of_scope` naming the
hunks left unread. A central declaration file can carry hundreds of hunks for
other product areas; reading them is not part of a scoped review. Do not write
that a file is explained while hunks remain unread. The same file can support
several events, and assigning it to one does not account for its other changes.

A milestone summary is a separate source to verify against the compared
versions. It does not by itself prove that a capability was available there.

### Repeat until the remaining work is accounted for

Start each session with the saved request and review, not a new selection of
high scores. The unfiltered queue below covers the whole index. For a focused
review, first use the overview and retrieval procedure in `scoping.md`; an
empty filtered queue does not establish whole-index completion:

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
```

An incomplete `check` exits 1 intentionally; read its JSON and continue.
`total` and `counts` cover the entire index, not the current page. `by_kind`
separates findings, source deltas and milestone leads so that an untouched
source inventory is visible even after many findings have been examined.

For each returned item in the confirmed scope, inspect the evidence and record
an event or a specific non-event decision. If evidence is missing, record
`unresolved` with the exact next check. Do not use a shell loop to generate
identical explanations for unexamined items. After saving the batch, run the same pending query again
with cursor 0 and without `--query` or `--after`. Decided items no longer appear;
the next items do. Repeat while pending items remain. If the count does not
decrease, inspect the record result instead of selecting a different sample.

For focused batches, retain the chosen path/kind retrieval filters while
continuing that query. Separately inspect supporting source and dependencies
outside those filters. A focused review over a broader index may remain
`PARTIAL` in whole-index accounting: report the assessed scope and untouched
remainder separately, not thousands of invented exclusion decisions.

Then page through `index --status unresolved` and the saved provisional events.
Perform their next checks when possible and update the decisions. `review
unresolved` is a different query: it lists unresolved graph references.
Recheck pending items after event revisions or refresh because these can
restore items to pending. Group related evidence across batches; batch
boundaries must not become event boundaries.

When context is nearly full, save the current decisions, source locations,
questions and next checks before continuing in a fresh context if the runner
supports it. Resume the same directory. A context-window limit is not a limit
on the number of events; the runner may still impose a separate total work
limit. If that limit is reached, report the unfinished counts and the reason.
Do not invent completion or silently reduce the scope.

## Define and revise events

An event should answer one specific question: what related change occurred?
Explain why its items belong together and how they differ from nearby work.
Source references, consumers, shared persisted keys and commit history can
establish relationships. A common name, flag, file or CL alone cannot.

Read previously saved events when analyzing another batch. Combine related
fragments or separate unrelated changes when the evidence requires it.
The graph is not a complete call graph, so inspect source relationships that
are missing from it.

## Record decisions

Create a JSON file with the following structure using the environment's file
editing mechanism. Replace example values with real IDs and observations.

```json
{
  "events": [{
    "title": "Describe the related change",
    "status": "provisional",
    "items": ["kind:actual-key"],
    "before": "Observed state in the earlier version",
    "after": "Observed state in the later version",
    "mechanism": "How the code changed and why these items belong together",
    "impact": "Affected consumers; identify any product-specific uncertainty",
    "conditions": "Relevant build, runtime and deployment conditions",
    "action": "Specific check or update, with the affected consumer location",
    "uncertainties": ["Question that still needs evidence"],
    "evidence": [{
      "item": "kind:actual-key",
      "supports": "The observation supported by this item"
    }]
  }],
  "dispositions": [{
    "id": "file:path/from/index.cc",
    "status": "unresolved",
    "reason": "Unexplained source section, missing evidence and next check"
  }]
}
```

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
```

`record` validates the proposed changes before writing. Every event member
needs an evidence explanation. Unknown IDs, duplicate primary membership and
decisions pointing to absent events fail validation. This checks the record's
structure and references, not whether its conclusions are true.

`confirmed` means the stated conclusion is supported within its stated scope.
`provisional` means an unresolved question could change the conclusion.
Unknown deployment status can remain a stated limit of a confirmed source
change; it does not justify claiming deployed availability.

Event IDs default to a hash of sorted item IDs, not wording or scores.
To revise an event, supply its existing `id`. To split or merge events,
include `remove_events: ["event:old-id"]` and replacements in one patch.
Items released from an event become pending unless reassigned.
Optional nonnegative `order` values control presentation, not discovery.

An evidence entry can use `item` for a finding or unchanged node, `url` for
an HTTPS source/CL/bug page, or `source` for hash-verified local evidence:

```json
{
  "source": {
    "side": "to",
    "path": "path/to/consumer.cc",
    "sha256": "COPY_FULL_SHA256_FROM_SOURCE_RESULT",
    "start": 100,
    "end": 120
  },
  "supports": "What these source lines establish"
}
```

Use source line numbers, not diff-output line numbers. Read a URL before
citing its contents. Validation does not fetch URLs or verify that a source
supports the stated claim. An inaccessible issue remains missing evidence.

## Refresh after saving new evidence
 `chromiumdiff why --save` changes `report.json`. Refresh the review before
continuing, using its saved configuration. The CLI does not automatically
retain a prior `--cache` or `--source-repo` when they are omitted on `review
init --refresh`.

Run the following from the project root after saving the lookup. It preserves
both cached-only and Git-backed reviews without guessing their paths:

```bash
python3 - out/upgrade/review <<'PY'
import json
import subprocess
import sys
from pathlib import Path

directory = Path(sys.argv[1]).resolve()
index = json.loads((directory / "review-index.json").read_text(encoding="utf-8"))
inputs = index["inputs"]
command = [sys.executable, "-m", "chromiumdiff", "review", "init",
           inputs["report"], "--directory", str(directory),
           "--cache", inputs["cache"], "--refresh"]
scope = inputs["source_scope"]
if scope["mode"] == "git":
    command.extend(["--source-repo", scope["repository"]])
subprocess.run(command, check=True)
PY
```

Read the result's warnings. With identical evidence, previous decisions are
preserved. Ranking or input-order changes alone do not invalidate them.
Context-only changes archive the old decisions, mark related events
provisional and related non-event decisions unresolved. Unrelated decisions
remain; new items are pending. This dependency check may revisit many events
under a shared condition, but does not mean those events should be merged.

Changes to source, snapshots or scope archive and reset the decisions.
If such a change was not intended, inspect the configuration before starting
another analysis. Additional files fetched by `review source --fetch` use a
separate cache and do not expand the baseline source inventory.

## Check completion

`review check` exits 1 for pending/unresolved items, provisional events,
invalid records or changed inputs. Exit 0 means all indexed items have valid
decisions. It does not prove semantic completeness or product safety.
The rendered report marks incomplete analysis as `PARTIAL`.

For final delivery of a whole-index review, use:

```bash
python3 -m chromiumdiff review render out/upgrade/review --require-complete
```

This exits 1 without writing or replacing `review.md` if items or events are
unfinished. For a recorded item selection, use `--require-selection-complete`
as described in [selection.md](selection.md). It requires that selection to be
complete while preserving whole-index PARTIAL when items outside it remain
pending. The ordinary `render` command remains available for a clearly labelled
partial report; its exit 0 only means the file was written. Neither command
verifies the meaning of the agent's explanations.

Before delivery, review event boundaries, source support, conditions and
remaining file hunks. A short summary may select key events, but the linked
full report must contain all supported events. A scoped review is delivered
when its confirmed scope is accounted for: report that scope, the total and
decision counts, counts by item kind, provisional events, and the items left
outside the scope. If a resource limit, missing evidence or a user-requested
stop leaves work incomplete inside the scope, report which one and the next
checks. Otherwise continue from the saved state; finding a convenient number
of events is not a stopping condition. Lack of time, a low score or difficulty
does not make an item out of scope or explain its effect.

Independent evaluation needs fixed source versions, input hashes, tool/skill
versions, inference settings and resource limits. A fresh agent must not see
expected event names or earlier answers. Repeated trials should compare
meaning, omissions and incorrect grouping, not identical prose. Structural
tests and valid record formats are not substitutes for that evaluation.
An independent evaluator must also work in saved batches across the declared
evaluation scope. Reviewing a sample can assess those sampled claims, but
cannot establish full event recall or validate the unexamined decisions.
