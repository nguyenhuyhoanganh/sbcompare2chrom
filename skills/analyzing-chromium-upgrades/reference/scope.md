# Accounting for a selected review scope

Use this after confirming the user's scope and inspecting its evidence inventory.
`request.md` records the product-language request. A saved `scope` records the
specific indexed items whose decisions must be complete for that request.
Retrieval filters alone do not define it.

Include the findings and `file:` source deltas in scope, plus supporting items
outside the selected paths when needed. Check implementation-only changes and
unresolved dependencies before deciding that this list represents the request.
Do not select only high scores or only parsed findings. Unchanged graph nodes
remain supporting evidence; they are not indexed decision items.

## Record the selection

Read the current `fingerprint` from `review check`. Create a JSON patch using
actual IDs from the index:

```json
{
  "scope": {
    "description": "The user's confirmed scope and the boundary of this selection",
    "fingerprint": "COPY_CURRENT_REVIEW_FINGERPRINT",
    "items": ["kind:actual-key", "file:path/from/index.cc"]
  }
}
```

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/scope.json
python3 -m chromiumdiff review check out/upgrade/review --scope
```

Run from the repository root. The scope can be recorded in the same patch as
events and dispositions. Empty, duplicate, unknown or stale selections fail.
Replacing the scope archives the previous selection in `scope_history`.
Use `"scope": null` only to explicitly clear it; that cannot pass a scope gate.

## Interpret completion

Every `check` still returns whole-index counts and a separate `scope` object:
`configured`, `description`, `total`, `outside_scope`, `counts`, `by_kind`,
`provisional_events` and `accounting_complete`. Without a scope, only
`configured: false` and `accounting_complete: false` are returned there.

Ordinary `check` exits according to the whole index. `check --scope` exits 0
only when the recorded scope is configured, valid and has no pending/unresolved
items or provisional events touching it, and input verification passes.
Unfinished work outside it remains visible. Neither result verifies that the
selected items cover the user's intent or that the explanations are true.

A completed selected scope can be rendered with:

```bash
python3 -m chromiumdiff review render out/upgrade/review --require-scope-complete
```

The report retains the whole-index `PARTIAL` status where appropriate and adds
`Scope accounting: COMPLETE` separately. The gate refuses to overwrite output
when the selected scope is absent or unfinished. Plain `render` still produces
an explicitly partial draft. `--require-complete` remains the whole-index gate;
it is mutually exclusive with `--require-scope-complete`.

Identical inputs preserve the scope. A context-only refresh retains its item
selection, pins it to the new fingerprint and reopens affected decisions.
A source/snapshot/baseline change archives and clears the scope; confirm a new
selection against the new index before claiming scope completion.
