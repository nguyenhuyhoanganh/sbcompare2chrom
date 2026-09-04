---
name: investigating-chromium-root-causes
description: Traces one Chromium change back to the review that made it and the bug that review was fixing, then judges whether that cause actually explains the symptom being reported. Use when asked what a specific finding really means, why a flag flipped, what a change was for, which review or issue to read, what broke after a Chromium upgrade and why, or when a symptom is reported and no finding obviously accounts for it. Works on one identifier or one symptom at a time. Use analyzing-chromium-upgrades instead to produce a full ranked report of everything that changed between two versions.
---

# Investigating Chromium root causes

A report says **what moved**. This answers **why it moved, and whether that
explains the thing you were asked about.**

The report cannot do it. It compares two trees, and a tree holds no intent —
`disabled → enabled` is the whole of what a diff can say. The intent lives on
Chromium's review server, and this skill goes and gets it.

## Three questions, routinely collapsed into one

Almost every wrong answer here is one of these answered with another's
evidence.

| # | Question | Evidence that settles it |
|---|---|---|
| 1 | What changed? | `report.json` — the signal, the delta, `path:line` |
| 2 | Why did Chromium change it? | the CL, and the **issue** the CL cites |
| 3 | Why does *our* build break? | our tree, read against 1 and 2 |

**A signal is not a cause.** `ipc_signature_change` says a shape moved. It does
not say why anyone moved it, and it never says your symptom came from it.
Reporting a signal as a root cause is answering 2 with 1's evidence, and it is
the failure this skill exists to prevent.

**A CL is not the defect.** The CL says what was *done*. The issue says what was
*wrong*. Someone asking "what is the actual error" is asking for the issue.

**Nothing here reaches question 3.** The tool compares Chromium against
Chromium. Say so, every time, rather than letting a confident answer to 2 read
as an answer to 3.

## Workflow

```
- [ ] 1. Pin the question to one identifier
- [ ] 2. Get the row, or establish there is none
- [ ] 3. Get the CL and the issue
- [ ] 4. Read the CL's own words and its own diff, and the issue behind it
- [ ] 5. Test the causal claim against the symptom
- [ ] 6. Answer at the evidence rung you actually reached
```

### Step 1: Pin the question to one identifier

Everything downstream is keyed by `uid` = `kind:key`, for example
`base_feature:BackForwardCachePauseMicrotasks` or
`mojo_field:blink.mojom.CommitNavigationParams.early_hints_preloaded_resources`.

**Given a finding, a flag name, or an identifier** — you already have it.

**Given a symptom** ("downloads page lost a toggle", "extension pages hang") —
the report is indexed by declaration name, not by symptom. Grepping it for the
words in the complaint finds nothing and means nothing. Map the symptom to a
surface first: **[reference/symptom-to-uid.md](reference/symptom-to-uid.md)**.

If the request names several things, do them one at a time. A batch answer
hides which evidence belongs to which claim.

### Step 2: Get the row

```bash
python3 skills/investigating-chromium-root-causes/scripts/why.py \
  out/M148_to_M151 BackForwardCachePauseMicrotasks
```

The search takes a uid, a key, a name, or a path fragment. Many matches print a
ranked list and stop, so re-run with one uid. No match at all is **not** an
answer — go to **[reference/no-row.md](reference/no-row.md)** before saying
anything about it.

### Step 3: Get the CL and the issue

The same command does it. If the finding has not been resolved before, the
script looks it up against Gerrit and prints the result; if it has, it prints
what is stored. Options:

| Option | Default | Use when |
|---|---|---|
| `--budget N` | 600 | a busy declaration file was declined; raise it |
| `--save` | off | you want the answer written back into `report.json` |
| `--json` | off | you need the raw block rather than prose |

What a `serve` session finds is saved to `report.json` and nowhere else.
`report.md` and `report.html` on disk are still what the run wrote, so
re-render before handing either to anyone:

```bash
python3 -m chromiumdiff report out/M148_to_M151/report.json --format both --out out/M148_to_M151/report
```

That is also what puts the groupings in: findings sharing a CL are joined when
the lookup brings the CL in, and `report.md` names the group in each finding's
own section — the part a reader pastes into a ticket.

It needs network access to `chromium-review.googlesource.com`. `python3 -m
chromiumdiff check` verifies that host.

**Serving is the alternative, not the requirement.** `python3 -m chromiumdiff
serve <dir>` gives a human the same lookup by clicking a row. Offer it when a
person will be reading; use the script when you are.

**Every CL carries a verdict, and the verdict caps what you may claim.**

| Verdict | You may say |
|---|---|
| `introduced` | "this CL made the change" — an added line inside the declaration carries the new value |
| `exact` | "this CL changed a line carrying the identifier" |
| `moved` | "the declaring file was renamed by this CL; no line changed" |
| `declares` | "this CL edited the declaration's body" — likely, and say why it is not `exact` |
| `described` | "the CL's own title names it" — no diff was read |
| `crowded` | **nothing about cause.** These edited the same declaration; read the list as that declaration's history |
| `touched` | **nothing about cause.** These merely touched the file |

Quoting `crowded` or `touched` as the cause invents a cause. The script labels
both `LEAD ONLY` for that reason.

### Step 4: Read the evidence, not the summary of it

Work outward in this order, and stop as soon as the answer is sufficient:

1. **The issue title.** Usually the actual defect, in one line.
2. **The other CLs citing that issue.** Click the issue chip on the CL you
   think is the right one; the history opens under it, and a second issue
   opens under the first rather than replacing it. This is the fix history —
   the shape of the problem, including whether it was serious enough to merge
   back to released branches. A `[M148]` or `[m147]` prefix on a CL subject is exactly
   that, and it is strong evidence the bug hurt real users.
3. **The CL's own words and its own diff**, whenever the answer matters — and
   always before quoting a CL in a ticket, whenever the verdict is `declares`
   or `described`, and whenever the subject reads as unrelated to the finding:

   ```bash
   python3 skills/investigating-chromium-root-causes/scripts/cl.py 7982397
   python3 skills/investigating-chromium-root-causes/scripts/cl.py \
     7982397 federated_auth_request.mojom --find 'url.mojom.Url? url'
   ```

   **Do not judge relevance from the subject.** Chromium subjects are
   `[area] what`, and the area is the author's word for the surface, not the
   identifier — `[sub apps] change web api` is the CL behind
   `SubAppsServiceRemoveResult.manifest_id`. Measured over 84 Mojo and Web IDL
   rows, the full message names the identifier in 39; reading the rest, all
   but five are unmistakable in the author's vocabulary.
   **[reference/reading-a-cl.md](reference/reading-a-cl.md)** is how to read
   both, and what each level of evidence lets you claim.

**A restricted issue is normal, not a failure.** Around four in ten linked
issues answer HTTP 403 — security, abuse, or Google-internal components. The
CLs stay public and their subjects carry the story. Report the fix history and
note the closed door; do not report the tool as broken.

### Step 5: Test the causal claim

Before writing an answer, put the claim against these. Each one has produced a
confident wrong answer.

- **Does the date fit, at both ends?** A CL merged before the *from* version's
  branch point is in both trees and cannot explain a difference. A CL merged
  after the *to* version's branch point is not in the released tree at all —
  `Cr-Branched-From` in each tag gives both dates. The lookup enforces both,
  and a served row written under the older, wider window is recognised and
  asked again rather than served — so a date past the target's branch point on
  a served row means something else, and is worth reporting.
- **Does the direction fit?** A flag going `enabled → disabled` is not explained
  by a CL titled "Enable …". Check which way the delta actually went.
- **Is the CL about this fact, or about the file?** A file touched by a rename,
  a reformat and the real change reports all three. `introduced` and `exact`
  discriminate; `declares` does not, on its own. The diff settles it, and four
  questions settle the diff: does a removed line carry the finding's
  before-value, does an added line carry the after-value, is the change inside
  the declaration the finding names, and is it more than a reindent? Three
  yeses and the CL is the cause; one no and it is context. Gerrit marks a
  reindent `common: true` and `cl.py` prints it `~`, because counting one as
  an edit is how a reformat becomes evidence.
- **Does the mechanism reach the symptom?** A flag flip explains a behaviour
  change on the platform where the flag flipped. Read
  `platform_state.windows`, never `default_state`.
- **Is this the cause, or a step in the story?** Launch → revert → reland is one
  fact and several CLs. The oldest CL is where it starts; the newest is where it
  currently stands. Report both.

If a check fails, the CL is context, not cause. Say which.

### Step 6: Answer at the rung you reached

```markdown
**What changed:** [the fact, with `path:line`, and which direction]
**Why:** [the issue's defect in one sentence, then the CL that acted on it]
**The history:** [launch/revert/reland and any merge-backs, oldest first]
**Confidence:** [one line from the table below, with the verdict named]
**What this does not establish:** [that it affects our build — always]
**To check next:** [the identifier to grep for in our tree]
```

| Say | When |
|---|---|
| The cause is CL N | the diff shows the finding's before-value removed and its after-value added, inside the declaration |
| The likely cause is CL N | `introduced` or `exact` with a date and direction that fit, but the diff not read |
| Related, not shown to be the cause | `declares` or `described`, or several CLs and one story |
| Candidates, not a cause | `crowded` or `touched`, or the checks in step 5 fail |
| Not established | the lookup missed, failed, or was declined — say which |

The top row needs the diff. Rung 4 of the evidence ladder in
[reference/reading-a-cl.md](reference/reading-a-cl.md) is the only one that
supports the word "caused"; everything below it supports "names", "touched",
or "was found by". **Report the highest rung you actually reached, and say
which it is** — a row answered from a verdict and written up as though the
diff had been read is the failure this skill exists to prevent.

Never round the last two up. "Candidates" written as "the cause" is the single
most damaging output available here.

## Worked example

Question: *"`BackForwardCachePauseMicrotasks` went from disabled to enabled at
M148 → M151. What is that, and does it matter?"*

The report alone says: score 75, `behaviour`, signals `enabled_by_default` and
`default_flip_on`, `disabled → enabled` on Windows, at
`third_party/blink/common/features.cc:168`. Read as a launch, which is wrong.

The lookup returns two CLs and two issues:

```
CL 7747043  2026-04-10  [declares]  Disable BackForwardCachePauseMicrotasks
CL 7789307  2026-04-23  [declares]  Enable BackForwardCachePauseMicrotasks by default

issue 500975618
  Extension iframe causes Promises to stall in all extension pages after navigation
    CL 7747043  2026-04-10  Disable BackForwardCachePauseMicrotasks
    CL 7756901  2026-04-13  [m147] Disable BackForwardCachePauseMicrotasks
    CL 7757083  2026-04-14  [M148] Disable BackForwardCachePauseMicrotasks
    CL 7763401  2026-04-21  Do not ... pause microtasks for extension iframes
issue 501771345 (RESTRICTED)
    CL 7774414  2026-04-22  Disable BFCache for pages with extension subframes
    CL 7789307  2026-04-23  Enable BackForwardCachePauseMicrotasks by default
```

**The answer inverts the report.** This is not a launch. The feature was on, it
stalled every Promise on extension pages after a navigation, it was turned off
and merged back to M147 and M148 as an emergency, the real bug was fixed
narrowly, and then it was turned back on. `disabled → enabled` across our two
versions is the *restoration*, and the thing worth testing is the thing that
broke: extension pages with iframes, Promises after navigation.

No diff could produce that, and no amount of reading `features.cc` would either.

Confidence: likely cause — both CLs are `declares`, not `exact`, because the
edit is in the declaration's body rather than on the line naming the flag. The
issue history is what makes it convincing, not the verdict.

## Reference

- **[reference/reading-a-cl.md](reference/reading-a-cl.md)** — the evidence
  ladder and what each rung lets you claim; why the author's vocabulary is not
  the identifier's; how to read a commit message and a diff, and the four
  questions a diff answers that nothing else does.
- **[reference/no-row.md](reference/no-row.md)** — every way a lookup comes
  back empty, what each licenses you to say, and the one sentence you may
  never write.
- **[reference/symptom-to-uid.md](reference/symptom-to-uid.md)** — starting from
  a user-visible symptom instead of an identifier.
- **`../analyzing-chromium-upgrades/reference/traps.md`** — the ways to reach a
  wrong conclusion from a finding. Read before interpreting any removal.
- **`../analyzing-chromium-upgrades/reference/signals.md`** — what each signal
  means.

## What this cannot establish

State these alongside the answer, not instead of it.

- **That the change affects a particular product.** Chromium is compared
  against Chromium. Grepping your own tree for the identifier is the step that
  answers it, and this skill does not take that step for you.
- **That a CL naming the change caused the symptom.** It establishes that a CL
  edited the thing inside the window. Step 5 is the gap, and it does not always
  close.
- **What happened inside a function body.** Declarations only.
- **Anything outside the repository** — Finch, enterprise policy, launch
  scripts. A flag whose default flipped can still be overridden there, and the
  override is invisible here.
