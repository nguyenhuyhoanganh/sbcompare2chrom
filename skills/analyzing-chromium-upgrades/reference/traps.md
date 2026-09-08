# Limits of source-based conclusions

MUST read this reference before drawing conclusions from source evidence.
For every applicable limit below, perform the check or retain the uncertainty.

Use this reference when interpreting absence, platform conditions, API
availability or compatibility. The checks apply to any identifier. A source
comparison establishes differences between versions; deployment and actual
failures require additional evidence.

## 1. Removed flag versus removed capability

A removed feature flag may indicate that its enabled branch was retained,
its implementation was removed, or another condition replaced it.
The last recorded default does not distinguish these outcomes.

Read the old flag declaration, both versions of its consumers and any
replacement. Check configurations or code that still refer to the removed
flag. State that behaviour is retained or removed only when the implementation
supports that conclusion. Do not infer permanent rollout from flag deletion.

## 2. Removed declaration versus moved declaration

A declaration missing from one file may exist elsewhere in the target version.
Search for its key, source identifier, persisted value and relevant consumers
at the exact target ref. Follow renamed files when necessary.

Two declarations with similar names are not necessarily replacements. Confirm
their relationship through source usage, bindings or commit history. Shared
flags, paths and the tool's clusters identify relationships to investigate;
they do not establish a migration or its date.

Searching a partial cache cannot establish tree-wide absence. If the required
files are unavailable, record the unresolved scope rather than calling the
capability removed. See [history.md](history.md) for exact-ref source searches.

## 3. Syntax changes versus declaration changes

A macro or declaration syntax change can preserve the same extracted meaning.
For example, one macro form can supply a feature string explicitly while
another derives it from the C++ identifier.

Compare the resulting name, default and conditions rather than source text
alone. The parser normalizes supported forms; inspect unsupported forms and
parser coverage before accepting a large set of apparent additions/removals.

## 4. External strings versus source identifiers

A C++ identifier and the string used by external configuration are different
identities. A syntax migration can change the derived string even when the
C++ identifier stays the same.

Check both `name`/key and `var` on the two versions. If the string changes,
inspect external settings using it. If only the C++ identifier changes,
inspect source references. Confirm aliases or migration handling before
claiming a specific consumer fails.

## 5. Platform-specific defaults

Read `platform_state.windows` for C++ and Mojo declarations, and the recorded
Windows status for Blink. General defaults can differ from platform-specific
values. A `conditional` value means non-platform conditions remain unresolved.

Inspect the complete condition and the product's build/runtime configuration
when needed. Source defaults do not measure the active Finch configuration.
Do not substitute a default from another platform.

## 6. Declared UI versus visible UI

Routes and controls can be declared behind separate conditions. Both old and
new UI can exist in source during a migration without both being visible.

Read route/template conditions, the values supplied by handlers and relevant
feature checks on both versions. Follow additional visibility code when
present. A removed route is a source observation, not proof that a page used
by the user disappeared during this comparison.

See [settings-screen.md](settings-screen.md) for source locations and the
relationship between routes, handlers, preferences and consumers.

## 7. Exact versions versus milestone numbers

A bare milestone can resolve to a different patch release on a later run.
Different patch releases may contain different behaviour.

Record the exact refs from the report. Use those refs for source and history
queries. Do not use the current checkout or the newest release as an
unmentioned replacement for either side.

## 8. Comparison scope and source configuration

Target sets, partitions, completeness mode and available files affect which
facts exist in a snapshot. Compare compatible inputs and inspect coverage
warnings. A full run covers the files its targets name, not all code or
syntax.

Adding `--refresh` does not repair a wrong scope choice. Keep the intended
target set and partitions when rebuilding a comparison. When refreshing a
review after a CL lookup, preserve its saved cache and optional Git repository
as described in [investigation.md](investigation.md).

The cache can contain files acquired for other analyses. The source inventory
may therefore include more files than the original declaration scan. State
both scopes. Files fetched later by `review source --fetch` are additional
evidence, not an automatic extension of the original inventory.

## 9. Build exclusion outside ordinary preprocessor conditions

Mojo attributes such as `[EnableIf=is_android]` can restrict a declaration.
A member can also inherit a condition from its enclosing declaration.
The tool records supported conditions in `platform_state`.

Build rules may exclude files without an inline condition. A platform-specific
path is useful evidence, but inspect all declaration locations and relevant
build rules before excluding a key. A duplicate declaration outside that
directory may still be relevant to Windows.

A zero score reflects the classifier's platform interpretation, not a reason
to skip the item without checking that interpretation. An Android-only change
can be marked out of scope for a Windows review with the supporting reason.
It is not automatically a parser error just because it appears in the input.

## 10. IPC contract changes versus actual failures

Matching generated bindings from one Chromium revision are not evidence of
a mixed-version failure. Identify the actual consumer before describing the
impact of a Mojo signature or layout change.

Check whether any relevant implementation or caller is maintained outside
the upstream tree, whether a component ships independently, and whether
communicating processes can use different interface versions.

Report the observed contract change even when product impact is unknown.
State build failure or runtime incompatibility only with evidence about those
consumers and versions. For enums, inspect extensibility, defaults and
generated handling before describing unknown-value behaviour.

## 11. API declaration versus API availability

An IDL member may have its own runtime condition or inherit one from its
interface. Exposure, secure-context requirements, build conditions and
runtime configuration may impose additional restrictions.

`web_api_added_live` means the classifier evaluated the recorded conditions
as allowing API calls. It does not prove universal availability.
`web_api_added_gated` describes a recorded default restriction; it does not
prove that all override or trial contexts are unable to use the API.

Inspect both interface and member declarations, the relevant runtime features
and consumers. Distinguish a newly declared capability, enabled source default
and verified availability in the user's build.

## 12. Removed switches and persisted preferences

If a switch declaration disappears, inspect argument parsing, aliases and
launch configurations that still pass it. A removed declaration does not by
itself prove which deployed launch commands stopped having an effect.

If a preference disappears, search for the persisted key, registrations,
readers, writers and migration code. Data may remain on disk even if the new
code no longer reads the key. Do not infer data loss, reset or a migration
from the bucket label or a key rename alone.

A wider declaration scan can locate a moved key. Determining stored-data
behaviour still requires reading the relevant implementation.

## 13. Implicit Mojo ordinals and comparison limits

The parser records lexical position for comparison inside declarations marked
`[Stable]`. Explicit ordinals are compared separately. Removing `[Stable]`
and losing recorded position is not the same observation as moving a member
between two recorded positions.

For a relevant non-stable interface with separately maintained consumers,
inspect its raw diff and generated message/field identifiers. An inserted
member can require investigation even if the declaration-based report does
not produce an ordinal-change finding.

Do not interpret the absence of that signal as proof of compatibility.
Establish which version combinations the product must support.
