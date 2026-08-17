# Comparing the fork against upstream

Read this instead of the uprev decision procedure whenever the comparison is
upstream against the fork rather than Chromium against its own future.

## Contents

- Why this is a different question
- The direction rule
- Decision procedure
- Provenance states: decision or debt
- Coverage states: what our build flags shadow
- What neither can tell you

## Why this is a different question

An uprev asks: Chromium changed, does it affect us? Every "removed" is upstream
housekeeping until proven otherwise.

A fork comparison asks: we differ, did anyone choose this? Every "removed" is
something **we** deleted, and the next rebase brings it back unless a patch
carries the deletion.

Same engine, same records, opposite readings. Running one with the other's
vocabulary scores every intentional divergence as upstream cleanup, or every
piece of upstream cleanup as a deliberate product decision.

This matters most for a fork built the usual way: take all of Chromium, modify
it, then every few milestones merge a newer Chromium and fix the conflicts.
After enough merges nobody remembers which differences were decisions.

## The direction rule

The comparison runs **upstream → fork**. Memorize this; every signal depends on
it.

| In the report | Means |
|---|---|
| `fork_dropped` | We removed something upstream still has |
| `fork_added` | We carry something upstream does not |
| `fork_default_override` | We ship a different default |
| `fork_modified` | Our declaration differs some other way |
| `fork_ui_removed` / `fork_ui_added` | We removed or added a page or control |

Buckets are re-worded to match: **Must fix** is divergence we depend on that a
rebase would silently undo; **Needs review** is divergence with no clear owner.
**New opportunity is never used** — both sides are code that already exists.

## Decision procedure

Stop at the first question that settles it.

1. **Does provenance say `stale`?** Our value matches an older Chromium exactly.
   Nobody decided this; a merge missed it. The report names the version we are
   stuck on. → debt, file it.
2. **Does provenance say `missing_new`?** Upstream added it during the range we
   merged through and no merge picked it up. → debt.
3. **Is it `shadowed`?** A vendor build flag selects our version. The value
   matching upstream proves nothing — upstream's branch is untouched by
   definition. Ask what our branch does, which is outside this tool.
4. **Is it `orphaned`?** Only we have it, and nothing marks it as ours. Usually
   upstream deleted it and our merge kept it alive. → debt, and often dead code.
5. **Is it `vendor_only` or `diverged`?** Someone wrote it. → decision. Record
   what it is for; that answer is the thing no future merge can reconstruct.
6. Otherwise `in_sync`. Say so and move on.

## Provenance states: decision or debt

`chromedrift provenance <fork> <oldest> ... <base> --fork-src <path>`

Upstream refs go **oldest first**. The series is the whole point: one upstream
version can only say "different", a series can say "different since when".

| State | Meaning | Debt? |
|---|---|---|
| `in_sync` | Matches the version we claim to be based on | no |
| `stale` | Matches an **older** upstream version — a merge missed this | **yes** |
| `diverged` | Matches no upstream version — someone wrote it | no |
| `missing_new` | Appeared during the series; no merge took it | **yes** |
| `missing_old` | Present since the oldest version; we dropped it | no |
| `vendor_only` | Only we have it, no upstream equivalent | no |

`stale_by_version` in the output is the headline number: it names which
milestone each group of declarations is still frozen at.

## Coverage states: what our build flags shadow

Printed by the same command when `--profile` supplies `vendor_markers`.

| State | Meaning |
|---|---|
| `untouched` | Upstream's declaration, no vendor guard |
| `shadowed` | A vendor build flag selects our version instead |
| `modified` | No guard, but the declaration differs |
| `absent` | Upstream has it, we do not |
| `vendor_only` | Only ours, and a vendor marker confirms we wrote it |
| `orphaned` | Only ours, and **nothing** marks it as ours — usually upstream deleted it and our merge kept it |

`vendor_only` and `orphaned` look identical in a plain diff and mean opposite
things: one is a decision, the other is debt.

`guards_used` lists which vendor flags do the shadowing and how much each
covers. A flag covering hundreds of declarations is a fork-within-a-fork and
deserves an owner.

**If `shadowed: 0`** and you know the fork shadows upstream, the marker names in
`vendor_markers.macros` are wrong. Get them from the real build files rather
than guessing; the analysis is skipped, not approximated, when markers are
absent.

## What neither can tell you

State these limits in a fork report.

- **Why.** Both answer *that* we differ and *how far back*. Neither can say
  whether it was chosen. A commit message, a bug id or an owner settles it, and
  none are in the data.
- **What our branch actually does.** Shadow analysis finds which declarations a
  vendor flag covers, not how our implementation behaves.
- **Anything not declarative.** Logic inside function bodies, TypeScript
  behaviour, resource and string edits.
- **Build reality.** The tool reads declarations, not the GN graph. A
  declaration present in the tree may not be compiled into the shipped binary.
