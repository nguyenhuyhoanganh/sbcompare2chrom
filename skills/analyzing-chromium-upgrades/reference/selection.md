# Accounting for a recorded item selection

Use this after confirming the user's scope and inspecting its evidence
inventory. Three different things are named here, so each one keeps its own
word: the **scope** is the product-language request, recorded in `request.md`;
the **selection** is the list of indexed items whose decisions must be complete
for that request, saved as `selection` in `review.json`; `source_scope` is which
files the declaration scan read. Retrieval filters define none of them.

Include the findings and `file:` source deltas the request covers, plus
supporting items outside the selected paths when needed. Check
implementation-only changes and unresolved dependencies before deciding that
this list represents the request. Do not select only high scores or only parsed
findings. Unchanged graph nodes remain supporting evidence; they are not indexed
decision items.

## Record the selection

Read the current `fingerprint` from `review check`. Create a JSON patch using
actual IDs from the index:

```json
{
  "selection": {
    "description": "The user's confirmed scope and the boundary of this selection",
    "fingerprint": "COPY_CURRENT_REVIEW_FINGERPRINT",
    "items": ["kind:actual-key", "file:path/from/index.cc"]
  }
}
```

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/selection.json
python3 -m chromiumdiff review check out/upgrade/review --selection
```

Run from the repository root. The selection can be recorded in the same patch as
events and dispositions. Empty, duplicate, unknown or stale selections fail.
Replacing the selection archives the previous one in `selection_history`. Use
`"selection": null` only to explicitly clear it; that cannot pass the gate.

## Interpret completion

Every `check` still returns whole-index counts and, beside them, a `selection`
object. With a selection recorded its fields are `configured`, `description`,
`total`, `outside_selection`, `counts`, `by_kind`, `events`,
`provisional_events`, `accounting_complete` and `limit`. Without one, that
object holds `configured: false` and `accounting_complete: false`. A selection
the index can no longer validate also reports `invalid: true`.

Ordinary `check` exits according to the whole index. `check --selection` exits 0
only when the recorded selection is configured, valid and has no
pending/unresolved items or provisional events touching it, and input
verification passes. Unfinished work outside it remains visible. Neither result
verifies that the selected items cover the user's intent or that the
explanations are true.

A complete selection can be rendered with:

```bash
python3 -m chromiumdiff review render out/upgrade/review --require-selection-complete
```

The report retains the whole-index `PARTIAL` status where appropriate and adds
`Selection accounting: COMPLETE` separately. The gate refuses to overwrite
output when the selection is absent or unfinished. Plain `render` still produces
an explicitly partial draft. `--require-complete` remains the whole-index gate;
it is mutually exclusive with `--require-selection-complete`.

Identical inputs preserve the selection. A context-only refresh re-pins it to
the new fingerprint and reopens affected decisions, but only while the new index
still holds every selected item: enrichment can retire one — a `brief:` id is a
digest of the brief's own text — and the selection is then cleared, with
`review init` warning that it was. A source/snapshot/baseline change archives and
clears it outright. Either way, confirm a new selection against the new index
before claiming completion.
