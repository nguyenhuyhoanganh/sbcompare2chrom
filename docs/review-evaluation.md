# Evaluating meaningful Chromium upgrade reviews

The `review` workbench supplies evidence and accounting, not automatic semantic
event discovery. Unit tests establish deterministic retrieval and ledger
invariants. They do not establish that a fresh agent finds all meaningful
changes. That requires the protocol below.

## Blind trial

1. Pin the tool and skill revisions, exact Chromium refs, target set, platform,
   source-cache or Git inventory, evidence fingerprint, model/version, inference
   settings, context budget, total work budget and network evidence cutoff.
2. An independent reviewer examines source/CLs to establish events and evidence
   membership. Keep that gold outside the agent's accessible inputs. Do not
   construct gold solely from the script's classifications or worked examples.
3. A fresh agent starts with the upgrade question, SKILL.md and raw artifacts.
   It can execute documented commands and investigate source/CLs. It cannot
   inspect expected answers or previous reviews. Save its ledger and final text.
4. Independently adjudicate event meaning, conditions, causal claims, actionable
   advice, omissions and false merges/splits. A string-matching scorer cannot
   do this. Citations must entail the claims they support.
5. Repeat at least five times for the same frozen input. Compare core events
   and evidence membership, not identical prose. A partial run stays partial.

Both discovery and independent adjudication may need multiple saved batches.
A page size or context-window limit is not an event quota. For discovery,
repeat `review index --status pending` after recording each batch, then revisit
unresolved decisions and provisional events. Record whole-index counts from
`review check`, including `by_kind`, and use `review render --require-complete`
for a completed report. This rejects unfinished accounting, not false claims.

For adjudication, divide the frozen input scope into explicit work units and
save which units and claims have actually been checked. Include source-only
changes and explained/excluded decisions, not just the agent's chosen events;
otherwise omissions cannot be measured. Reconcile events that cross work-unit
boundaries before final scoring. A sampled assessment must state its sample
and unreviewed scope. It cannot establish full recall, and unreviewed expected
events, predicted events or dispositions must not receive passing judgments.
If a complete independent expected set cannot be established, full recall
remains unmeasured; do not redefine the selected sample as the whole release.

Include held-out version pairs and feature families, not just the development
pair. Remove named worked examples in one trial. Vary finding scores, buckets
and order while preserving source evidence. Include independently labelled
unrelated changes under common gates/CLs, related work across several CLs,
unchanged bridging facts and implementation-only changes. Synthetic renamed
fixtures probe invariants but do not replace real held-out Chromium cases.

## Structural scorer

Gold format (illustrative IDs, not an answer set):

```json
{
  "provenance": "Who independently reviewed which source/CLs, and when",
  "fingerprint": "OPTIONAL_EXACT_REVIEW_INDEX_FINGERPRINT",
  "events": [
    {"id": "reviewer-event-1", "items": ["kind:key-a", "kind:key-b"], "critical": true},
    {"id": "reviewer-event-2", "items": ["kind:key-c"]}
  ]
}
```

Gold primary memberships must be disjoint; shared evidence is not primary
membership. Use findings as the stable core where appropriate. The scorer
projects trial membership onto gold IDs; items outside that annotated scope
are reported as unadjudicated, not false positives.

```bash
python3 -m chromiumdiff review evaluate /path/to/gold.json /path/to/trial-1 /path/to/trial-2
```

Measures: exact event-member recall, finding recall, pair precision/recall,
overmerged groups, split events, missed critical events and pairwise event
partition Jaccard. Consistency requires equal evidence fingerprints. A perfect
score can still describe the wrong behaviour; semantic correctness and
unsupported claims remain explicitly unmeasured until adjudicated.

## Prepare and execute isolated trials

Two real Chromium file-scope cases are supplied in `tests/fixtures/review_cases`.
Their exact tags and per-side source hashes are pinned. Keep the separate
`tests/fixtures/review_gold` rubrics inaccessible to the executing agent.
The rubrics were authored from whole-file source deltas by the maintainer;
they still require an independent reviewer, not automatic acceptance as truth.
They cover five substantive contract/migration consequences in 143→147 and
an unrelated XR contract boundary in 147→151, plus comment-only and unchanged
controls. This is deliberately **not** an entire-release recall benchmark.

```bash
trial_root=$(mktemp -d)
python3 -m chromiumdiff review prepare-trial \
  tests/fixtures/review_cases/chromium-143-147-contracts.json \
  --directory "$trial_root/trial-1" --reference-mode core
```

Pass `--cache /path/to/cache` if nondefault. Missing/mismatched sources fail
explicitly; preparation does not fetch or invent empty files. Each workspace
contains the executable package, skill, `TASK.md`, source-derived report and
exact-version cache. It excludes tests, gold and prior reviews. `core` replaces
the analysis skill's domain references with neutral notices and keeps the
scoping, focused retrieval, analysis and history references with their Chromium
path examples redacted; `full` keeps the normal references. Metadata
records both the parent revision and actual staged reference digest.
`--seed 17` perturbs scores, buckets and input order without changing evidence.
Repeat into five new directories with the same tool revision/source case.

Execution can use a fresh interactive agent, or an explicitly supplied command:

```json
{
  "model": "EXACT_DEPLOYMENT_MODEL_REVISION",
  "context_limit": 200000,
  "context_limit_verified": true,
  "settings": {"description": "Record inference settings and total work budget"},
  "timeout_seconds": 3600,
  "command": ["/absolute/path/to/your-runner", "--workspace", "{workspace}", "--task", "{task}"]
}
```

```bash
python3 -m chromiumdiff review run-trial "$trial_root/trial-1" --runner /path/to/runner.json
```

There is no bundled inference service or implicit paid request. The command
runs without shell interpolation; placeholders replace whole argv elements.
Use environment-based credentials, never put secrets in the runner JSON or
argv saved as provenance. The runner must enforce its own filesystem/network
boundaries, actual context budget and descendant-process cleanup on timeout.
Staging is answer separation, not an OS sandbox. `run-trial` refuses a second
attempt in the same directory and saves exit/timeout status and output logs.

For an interactive run, use `collect-trial DIRECTORY --runner identity.json`.
Its identity file needs `model` and a unique actual `session_id`; also record
elapsed time, inference settings and the verified context limit if available.
If interrupted, record `failure` and preserve the partial ledger. Unknown
revision/context limits must stay unknown or unverified, not guessed as the
intended deployment profile. Collection validates artifacts; it never grants
semantic credit. A fresh retry belongs in a fresh directory.

## Adjudicate meaning and apply the gate

Generate the independent review form after execution, outside all trial inputs:

```bash
python3 -m chromiumdiff review assessment-template \
  tests/fixtures/review_gold/chromium-143-147-contracts.json \
  /absolute/path/trial-1/workspace/review /absolute/path/trial-2/workspace/review \
  --output /path/outside-trials/assessment.json
```

Supply all five reviews for a release check (two shown only to keep the example
short). The template pins the gold digest and each ledger digest. It starts
unresolved, without guessed mappings or passing judgments. An independent
reviewer fills in:

- `reviewer` and source/CL `provenance`.
- Every expected event's `predicted_event_ids` and all six checks: `meaning`,
  `transition`, `conditions`, `impact_action`, `citations`, `grouping`. Each
  needs `verdict` (`pass`, `fail`, `unresolved`), a specific `reason` and a
  nonempty `evidence` list of exact-version source locations/CLs. An omission
  has no predicted IDs and cannot earn credit.
- `reviewed_predicted_event_ids`: every actual output event, including extras
  outside the core gold memberships. `predicted_event_ids_to_review` is just
  the template's checklist, not an assertion of review.
- `dispositions`: the same verdict/reason/evidence structure for excluded and
  explained items, remaining file hunks and negative controls. This guards
  against calling every difficult item “explained” to clear accounting.
- `unsupported_claims`: explicitly `[]` if none after review; otherwise each
  claim needs `event_id`, `severity` (`major` or `minor`), `claim`, `reason` and
  source `evidence`. Do not omit an invented extra event just because it has
  no expected counterpart.

```bash
python3 -m chromiumdiff review evaluate \
  tests/fixtures/review_gold/chromium-143-147-contracts.json \
  /absolute/path/trial-1/workspace/review /absolute/path/trial-2/workspace/review \
  --adjudication /path/outside-trials/assessment.json \
  --manifests /absolute/path/trial-1/trial.json /absolute/path/trial-2/trial.json
```

Again supply all five runs/manifests. Use their canonical `review_directory`
paths as labels. With adjudication, exit 0 means the gate passed **for that
pinned case and runner only**; exit 1 means unmet requirements, and malformed
or stale assessments fail validation. Structural-only evaluation remains a
diagnostic, never a release approval.

The gate requires ≥95% adjudicated event recall in every trial, no missed
critical event, no major unsupported claim, adjudicated dispositions, complete
accounting, ≥5 distinct execution records, equal source fingerprints, frozen
tool/case/runner profile and a verified context limit of at most 200k. Pairwise
recovered core-event Jaccard must be ≥0.90. Structural splits/merges remain
visible, but an independently justified alternative narrative boundary can
receive semantic credit. Changes to prose invalidate its previous assessment.

The gate checks declarations and evidence freshness, not the identity or
honesty of the reviewer/runner. It cannot independently verify semantic truth
or prove a runner actually enforced its declared limit. Audit the execution
configuration and citations before accepting its verdict. Report metrics with
dataset size/scope. No finite suite proves discovery of every Chromium change.

## Current validation boundary

The repository includes synthetic invariant tests in `tests/test_review.py`
and `tests/test_review_trials.py`,
including arbitrary renaming, rank/order independence, unchanged bridges,
unparsed source deltas, cache ambiguity and atomic checkpoints. The existing
named M148→M151 scenarios remain regression questions, not a blind discovery
benchmark. The two source-pinned cases add reproducible cross-version inputs,
source-first rubrics, isolation, ablation and execution/adjudication commands.
They are a small evaluation corpus, not broad semantic certification.

On 2026-09-08, `python3 -m unittest discover -s tests -q` passed **615 tests**;
compilation, diff whitespace checks and the skill creator's `quick_validate.py`
also passed. Real-file staging, index/source/render and assessment-template
smoke checks succeeded: the first case has 59 indexed items, the second has
3, including a source-only comment delta; the unchanged control has no delta.
These smoke ledgers intentionally remain pending, not completed reviews.

Three cold-start attempts initialized ledgers but completed no event decisions;
two explicitly reported account usage limits. They are **not passes** and no semantic
recall/repeatability result is claimed. Five completed independent runs on the
intended deployment model, with independently checked rubrics and assessments,
remain necessary before declaring the release targets achieved. Do not treat
the synthetic gate's passing unit test as a real semantic evaluation.
