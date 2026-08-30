# Reading the CL itself

## Contents

- Why a verdict is not the end
- The evidence ladder, and what each rung lets you say
- The vocabulary gap: the author's word is not the identifier
- Reading the commit message
- Reading the diff
- Four questions a diff answers that nothing else does
- When the diff disproves the CL
- Commands

## Why a verdict is not the end

`why.py` tells you **how the tool found a CL**. `introduced`, `exact`,
`declares` are statements about a search, not about causation. The search
asked "does this CL's diff of this file touch this identifier"; it never asked
"is this the change the finding is about".

Most of the time those coincide. The gap is where wrong answers live, and the
only thing that closes it is opening the CL.

Do it whenever the answer matters: before quoting a CL in a ticket, whenever
the verdict is `declares` or `described`, whenever the subject reads as
unrelated, and whenever a row carries several CLs and you have to pick.

## The evidence ladder, and what each rung lets you say

Lowest to highest. Each rung is checkable; none of them is an opinion.

| Rung | Evidence | You may say |
|---|---|---|
| 1 | the file was touched | "these CLs edited the declaring file" |
| 2 | a verdict names the fact | "a changed line carries the identifier" |
| 3 | the commit message explains it | "the author says this CL did X" |
| 4 | the diff shows the before and after | "this CL made the change the finding reports" |
| 5 | the issue states the defect | "it was done because Y was broken" |

Rungs 1 and 2 come from `why.py`. Rungs 3 and 4 need `cl.py`. Rung 5 needs the
issue chip, or `why.py` on a served report.

**Report the highest rung you actually reached, and say which it is.** A row
answered at rung 2 and written up as rung 4 is the failure this whole skill
exists to prevent.

## The vocabulary gap: the author's word is not the identifier

This is the single most common reason a correct CL looks wrong.

Chromium subjects are written `[area] what changed`, and the area is the
author's name for the surface — the product, the team, the shorthand — not the
identifier the report holds. Searching the subject for the identifier and
finding nothing means almost nothing.

Measured over 84 Mojo and Web IDL rows of a real M148 → M151 run: the CL's
full commit message contains the identifier in 39. Reading the other 45,
all but five are unmistakable once the author's vocabulary is allowed:

| The finding holds | The CL is titled |
|---|---|
| `SubAppsServiceRemoveResult.manifest_id` | `[sub apps] change web api` |
| `TextAutosizerPageInfo.main_frame_width` | `[autosizer] Delete the text autosizer` |
| `blink.mojom.RTCMetadata` | `[RTCLogging] Add metadata parameter to finishDiagnosticLogging` |
| `payments.mojom.PaymentRequestEventData` | `Allow web-based payment handlers to indicate error (3/N)` |
| `CastStreamingWinHardwareH264` | `[Cast Streaming] Enable hw H264 encoding by default` |

So: **do not judge relevance from the subject.** Read the body, and read the
diff. The body usually names the struct, the file, and the reason; the diff
always shows the change.

`(3/N)` and `[2/3]` in a subject mean the change is split across CLs. The one
you were given may be the plumbing, and a sibling may be the part that matters.
The issue links them — that is what the issue chip is for.

## Reading the commit message

Four parts, and each answers something different.

- **Subject** — the area and the intent, in the author's words. Good for
  "what family of change is this", useless for "is this my identifier".
- **Body** — usually names the struct, the file, and the reason. This is
  where a Mojo change says which type moved to which type and why.
- **`Bug:` / `Fixed:` footers** — the issue. `Fixed:` closes it, `Bug:`
  references it; Chromium writes far more of the second.
- **Machine footers** — `Cr-Commit-Position: refs/heads/main@{#N}` is the
  proof it landed on main and where. Reviewers and `Change-Id` are rarely
  what you need.

A revert carries `revert_of` and a cherry-pick `cherry_pick_of_change` in
Gerrit's own record, which `cl.py` prints above the message. Those are more
reliable than reading `Revert "..."` out of a subject.

## Reading the diff

Gerrit returns a diff as blocks, and the shape matters:

| Block | Means |
|---|---|
| `ab` | unchanged, shown for context |
| `a` | removed |
| `b` | added |
| `common: true` | **the same content, differing only inside the line** |

The last one is a reindent or a reflow. `cl.py` marks it `~` rather than
`-`/`+`, because counting it as an edit is how a CL that reformatted a file
becomes an `exact` match for every declaration in it.

The two sides are the whole point. A finding records a declaration's before
and after; the CL that made that change is the one whose **removed** line
carries the before and whose **added** line carries the after:

```
  -   string? url;
  +   url.mojom.Url? url;
```

That is `blink.mojom.TokenError.url` changing type, and it is the evidence
`introduced` is built on — read directly rather than taken on trust.

**Search the diff for the changed value, not the identifier.** The identifier
is usually on unchanged lines too, and every one of those is noise. `cl.py
--find` only marks lines the CL changed, for that reason.

A file the CL renamed answers under the old path with the whole file as one
block and no rename marker. `cl.py` prints `(renamed from ...)` when Gerrit's
metadata says so; an "empty" diff on a removal is that, more often than not.

## Four questions a diff answers that nothing else does

Ask them in order. Stop at the first "no".

1. **Does the removed side carry the finding's before-value?** If the finding
   says `Vector2d → Vector2dF` and no removed line says `Vector2d`, this CL
   did not make that change.
2. **Does the added side carry the after-value?** Both sides is the strongest
   evidence available short of running the code.
3. **Is the change inside the declaration the finding names**, rather than
   elsewhere in the same file? A file of declarations gives every CL a line
   near every declaration.
4. **Is it more than a reindent?** Every marked line `~` and nothing `-`/`+`
   means a reformat, and a reformat causes nothing.

Three yeses and the CL is the cause. One no and it is context — say which.

## When the diff disproves the CL

This happens and is worth reaching for, because a disproof is a real finding.
Look for these:

- **The diff touches a different member of the same struct.** Common on Mojo:
  the CL edited the declaration's body, earned `declares`, and the member it
  edited is not yours.
- **The whole diff is `~`.** A reformat.
- **The change is in the other direction.** The CL removes what the finding
  says was added.
- **The date is outside the two trees.** `why.py` will not show these now, but
  a CL you reached from an issue history can be from any milestone.

When one holds, the row is not answered. Go back to the other CLs on it, raise
`--budget`, or report that the search reached the file but not the cause.

## Commands

```bash
# what the CL says about itself, and which files it touched
python3 skills/investigating-chromium-root-causes/scripts/cl.py 7982397

# the diff of one file, marking only changed lines carrying the value
python3 skills/investigating-chromium-root-causes/scripts/cl.py \
  7982397 federated_auth_request.mojom --find 'url.mojom.Url? url'

# the whole diff of that file, no marking
python3 skills/investigating-chromium-root-causes/scripts/cl.py \
  7982397 federated_auth_request.mojom --context 0
```

`--find` is repeatable; pass the before-value and the after-value together to
see both sides of the change at once.
