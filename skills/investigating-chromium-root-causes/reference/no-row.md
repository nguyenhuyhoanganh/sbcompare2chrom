# When a lookup returns no result

`chromiumdiff why` searches findings in `report.json` and then looks for
related CLs. No matching row and no matching CL are different results. Neither
by itself establishes that source or behaviour did not change.

## Part A — no matching finding

The helper prints `nothing ... matches`. Check the following possibilities.

### A1. The search does not match the report's identifier

Use the finding's `kind:key`, or search by a path fragment. A feature's
external string and its C++ identifier can differ. Mojo keys include their
namespace and enclosing declaration. Keep the actual cache path:

```bash
python3 -m chromiumdiff why out/DIR features.cc --cache "$cache_dir"
```

This still searches report findings, not arbitrary file history. A `file:`
or `brief:` ID from a review index is not a finding UID.

### A2. The file was outside the declaration scan

Inspect the run's target set, partitions and coverage. If the file was not
read, the report cannot establish whether its declarations changed.
A full run covers the files its targets name, not all code.

For a specific question, inspect the required source at both exact refs.
Rebuild a wider comparison only when needed for the user's scope, and keep
its output separate from an existing analysis unless replacement is intended.

### A3. The parser does not extract this syntax

File coverage and syntax coverage are different. A file can be cached while
some of its declarations are not represented as facts. Read its raw diff
rather than concluding that no matching finding means no change.

### A4. The change is in implementation code

A function-body change may produce no declaration finding. The review's
source inventory can still identify the changed file when it is cached or
in the selected Git comparison. Inspect `review source` and the relevant
consumers even when `chromiumdiff why` cannot resolve it.

For A3 or A4, use the
[direct source/history procedure](history.md).
It does not require a finding or a known feature name.

### A5. No relevant source difference was found

State which paths, refs and scope were actually compared. Do not generalize
that result to uncached files, external configuration or product behaviour.
Even unchanged declarations can have changed consumers or runtime conditions.

## Part B — a finding exists, but no explanatory CL

Inspect lookup warnings before interpreting an empty `changes` list.
Several limitations can apply to the same lookup.

### B1. No lookup was performed

A missing enrichment block means no stored lookup result is available.
Run the lookup if history is needed for the question.

### B2. Gerrit was unreachable

A connection or request failure establishes a retrieval problem, not an
absence of changes. Check access and retry when useful. If access remains
unavailable, preserve the source-level result and state the history limit.

### B3. The diff budget was reached

`diffs_read: false` means the relevant diffs were not read. Increase the
budget for the selected finding when justified. `--budget 0` disables the
diff cap; do not use it automatically for a large comparison.

### B4. Some requests failed

`failed_fetches > 0` means the returned evidence is incomplete. Successful
results may still support a bounded conclusion. Retry failed retrieval where
possible; cached successful results can be reused.

### B5. The candidate search was incomplete

`search_incomplete` indicates that the candidate list may omit relevant CLs.
Read the available candidates and use direct history if needed. Do not count
the incomplete list as all commits affecting the file.

### B6. The completed searches found no explaining match

If the relevant searches and diffs completed without B2–B5 limitations, the
result is still limited to those paths, identifiers, branches and search
rules. It does not identify the cause of the unmatched change.

Investigate renamed paths, generated sources, dependency updates and branch
history as applicable. Use the direct source/history procedure linked above.
State which searches failed to explain the observed difference rather than
asserting that the responsible commit must have a particular form.

## Retrying and command status

Use `--retry` to repeat a saved result while retaining successful HTTP cache
entries, including when raising `--budget`. `--refresh` refetches Gerrit data.
The JSON envelope carries `lookup.status` and `lookup.warnings`: `complete`,
`partial`, `unavailable` or `not_run`. These describe the lookup, not causality.
Exit 3 means incomplete/unavailable history; exit 1 means no finding matched;
exit 2 includes input and save failures. Stored `lookup_warnings` in the Gerrit
block retain additional retrieval limits from an earlier saved lookup.

## Reading the stored fields

| Field in `enrichment.gerrit` | Interpretation |
|---|---|
| Block absent | No stored lookup result |
| `diffs_read: false` | Relevant diffs were not read |
| `failed_fetches > 0` | Some requests failed |
| `search_incomplete` | Candidate search may be incomplete |
| `changes: []` | No matched CL was stored; check all limitations above |
| `found_by: "message"` | Candidates came from commit-message search; verify their diffs |

Do not treat inaccessible issues as supporting evidence. When saving new
lookup results, preserve the review's cache and Git configuration during
refresh, as described in the local
[saved-input procedure](review-inputs.md).
