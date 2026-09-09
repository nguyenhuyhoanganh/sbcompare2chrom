# Passing work to another skill

Invoke the destination skill by name and say what it should do. Do not read
its reference files or execute scripts inside its directory. Shared commands
remain in the repository-root `scripts/` directory.

Pass a short record with these fields; JSON is convenient but not required:

- `from_skill` and `to_skill`: skill names.
- `purpose`: one concrete question or requested result.
- `refs`: exact `from` and `to` refs from the report, not milestone aliases.
- `artifacts`: report/review paths, cache path and saved Git repository when
  present. State that paths are relative to the repository root, or absolute.
- `identifiers`: finding UIDs and/or exact source paths; a symptom without a
  UID stays a symptom, not a guessed identifier.
- `evidence`: observed before/after facts, source locations/hashes and examined
  CLs/issues, with what each supports. Label candidates and unread links.
- `limits`: unavailable evidence, incomplete searches and remaining questions.
- `return_to`: the calling task and what it needs back.

Use `investigating-chromium-root-causes` to trace one change or symptom when
an upgrade event needs causal evidence. Return the source transition, inspected
CL/issue evidence, causal confidence, symptom connection and next checks. The
calling analysis skill records the result in its own event ledger.

Use `analyzing-chromium-upgrades` when the user requests an upgrade-wide or
product-area review extending beyond a single cause. Pass the confirmed scope
and existing evidence; do not infer new areas, versions or declaration kinds.

The receiving skill verifies refs and evidence freshness, keeps the user's
scope and authorization, and reads its own local references. A handoff does
not mark items reviewed or establish a cause. If the report was enriched,
refresh an existing review with its saved inputs before recording decisions.
If the named skill is unavailable, return the missing capability and current
evidence limits to the caller instead of reaching into its files.
