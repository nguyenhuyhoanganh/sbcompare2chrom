# Event investigation and checkpoints

## Working set and coverage

Keep a compact event index and current questions in context. Open only the
finding leaves, nearby evidence and source slices needed for the current
question. The complete ledger stays on disk. Its dispositions are accounting
decisions, not output categories for the human report.

Every index item must eventually be one of:

- `event`: primary member of one event. Other events may cite it as supporting
  evidence without assigning it twice.
- `explained`: examined but no standalone report item is warranted; give the
  specific explanation and evidence/location, not merely "cleanup".
- `out_of_scope`: excluded by the user's declared scope, with a reason.
- `unresolved`: a concrete unanswered question and next check.

Items without a decision are `pending`. A source-delta item represents the
entire file delta: inspect remaining hunks even if some already support
finding-based events. One file can support many events; assigning it to one
does not explain every other hunk. Milestone summaries are independent leads;
verify applicability to the exact versions/platform or explain the gap.

## Event boundaries

Test each proposed group against one sentence describing a transition. Explain
what each member contributes and what distinguishes it from neighbouring work.
Useful relationships include bindings and ownership, consumer usages found in
source, migrations of the same persisted key, and history linking stages.

The workbench indexes relations its inputs declare; it is not a full
C++/TypeScript call graph. Follow unresolved identifiers and implementation
deltas with targeted source reading. Common flags can gate unrelated work;
CLs can mix refactoring with behaviour changes. Conversely, a single event can
span several CLs and unchanged bridging declarations. Do not require a known
feature name, signal or reference example before investigating a delta.

## Recording decisions

Create a JSON patch with your runtime's file-editing mechanism. Replace these
placeholders with actual IDs and conclusions; they are not discovery keywords:

```json
{
  "events": [{
    "title": "Describe the capability transition in the reader's language",
    "status": "provisional",
    "items": ["kind:actual-key"],
    "before": "Observed prior state",
    "after": "Observed new state",
    "mechanism": "How the evidence establishes one transition; why grouped",
    "impact": "Affected consumer or user; distinguish unknown product impact",
    "conditions": "Build/runtime/rollout conditions and what remains unknown",
    "action": "Specific verification or decision, with consumer/source locations",
    "uncertainties": ["Concrete question still needing evidence"],
    "evidence": [{
      "item": "kind:actual-key",
      "supports": "Which before/after observation this member supports"
    }]
  }],
  "dispositions": [{
    "id": "file:path/from/index.cc",
    "status": "unresolved",
    "reason": "Which remaining hunks/consumer need checking, and next step"
  }]
}
```

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review render out/upgrade/review
```

`record` validates the whole proposed ledger before writing. Every event
member needs an evidence explanation. Unknown IDs, duplicate primary members
and dangling dispositions fail. This checks traceability, not whether the
explanation is true. `confirmed` means the stated, bounded conclusion is
supported; `provisional` retains a material unanswered question. Unknown
rollout may remain an explicit condition of a confirmed source-level change.

Event IDs default to a hash of sorted member IDs, independent of wording,
score and arrival order. To revise, supply the existing `id`. To split/merge,
include `remove_events: ["event:old-id"]` and replacements in the same patch.
Released members become pending unless reassigned. Shared supporting evidence
belongs in `evidence`, not duplicate primary memberships.
Use optional nonnegative `order` values to arrange the final narrative by
reader consequence. This is your presentation decision; it does not filter
discovery or change event membership.

Additional evidence can cite an unchanged node ID, an HTTPS source/CL/bug URL,
or hash-pinned source from the `source` command:

```json
{
  "source": {
    "side": "to",
    "path": "path/to/consumer.cc",
    "sha256": "COPY_FULL_SHA256_FROM_SOURCE_RESULT",
    "start": 100,
    "end": 120
  },
  "supports": "What the consumer proves within these conditions"
}
```

Local source citations are checked against their hashes. Read cited URLs;
validation does not verify remote contents or whether they entail a claim.
Keep inaccessible bug links as unknowns instead of claiming to have read them.

## Completion and reproducibility

`check` exits 1 for pending/unresolved items, provisional events, invalid
records or changed local input. Exit 0 establishes accounting completion only.
The rendered report labels an incomplete ledger `PARTIAL` and includes scan
coverage, source-inventory limits and disposition counts.

Reconcile events across batches before delivery. Inspect remaining references
relevant to the conclusions; check for duplicated, split or overmerged stories.
When resources run low, save the patch and next questions; resume from the
ledger instead of restarting a score-ranked skim.

The index pins refs, input fingerprints, snapshot hashes and source roots.
`review init ... --refresh` preserves decisions if evidence is identical (rank,
bucket and order are not evidence). On context-only changes it archives the old
ledger, follows both old/new declared relationships to mark affected events
provisional and affected non-event decisions unresolved. Disconnected work is
retained; new leads are pending. Recheck provisional event boundaries as well
as their wording. This conservative dependency check can reopen many events
under a broad gate/CL; it does not claim all those events are one change.
Source, snapshot or scope changes archive and reset baseline decisions.
Contextual `source --fetch` uses a separate
supplemental cache and does not increase baseline scan coverage.

For independent evaluation, pin the model/version, skill/tool revisions,
exact refs, evidence fingerprint, network cutoff and resource budget. A fresh
agent gets the broad question and skill, never expected event names. Build the
expected list independently from source/CLs. Test held-out version pairs and
families, removed examples, shuffled rows, changed scores, unrelated changes
under shared gates, and unchanged bridges. Compare coverage and false
merges/splits, not exact prose. Structural metrics still need semantic review.
