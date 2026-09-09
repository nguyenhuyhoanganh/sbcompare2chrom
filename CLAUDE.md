# Working in this repository

## Before calling a skill in `skills/` done

Eight defects were found by reading each `SKILL.md` against the code and
against a real `report.json`. **The suite passed with all eight present.**
Check them by hand.

1. **Every identifier the file names must exist in the artifact it tells the
   agent to read.** Signal ids appear zero times in `report.md` — it prints
   labels. `owner` was named as a field on a finding and never was one.
2. **Run every command as written, on a tree where only `run` has happened.**
   `serve out` was in the file; the run writes to `out/<pair>/`.
3. **Say where commands run from.** Every path is relative to the repository
   root, and `python3 -m chromiumdiff` fails anywhere else.
4. **The workflow checklist and the step headings must match one to one.**
5. **Check every "skip X" against what it hides.** "Skip Housekeeping" hid
   the unconfirmed removals a later step requires. That bucket was split for
   this reason, so check the instruction against the bucket's real contents,
   not against its name. Splitting it did not settle the instruction: the
   same skip then hid the 175 retired flags, which the *Fixed outside the
   repository* step calls always actionable and 169 of which appear nowhere
   in `report.md`. Re-read every skip after every change to what it skips.
6. **Define each term before first use, and drop terms the agent never sees.**
   `fact` appears nowhere in its input or its output.
7. **One word, one meaning per file.** `verdict` was both a provenance label
   and a report heading. `surface` was four things at once: the fact kind, the
   body of declarations coverage is measured over, the `chrome://` screen a
   WebUI fact sits on, and the web API surface. A row of `report.html` shows
   five naming vocabularies side by side — bucket, kind, kind group, column
   header, filter — so a word used in two of them names two things in one
   glance. `TestEverySignalIsClassified` holds that, reading the headers and
   filter labels off a rendered page rather than from a list here.
8. **Re-measure every figure; never copy one.** A figure must name the version
   pair it came from. Measure with the
   function the code measures with: counting `signals[0]` where the report
   uses `leading_signal` gave 19 signals where there are 18, and 39 where
   there are 38, twice, and both numbers looked right. Then check the
   function's empty answer. `leading_signal` returns `""` for a change with
   no signal, so a set built over it holds the empty string and 37 signals
   count as 38 — the third wrong number on that line, written by the fix for
   the second. `TestTheSummaryTalliesSayWhatTheyCover` holds the shape:
   `by_bucket` and `by_group` partition the findings and `by_signal` does
   not.

Two more, cheap to avoid: write where a field *is* rather than what does not
exist, and do not state a prohibition the code does not enforce.

## Elsewhere

- Each skill owns its references and private scripts. Shared scripts live in
  the repository-root `scripts/` directory. Cross-skill handoffs use the other
  skill's name and purpose, never a path to its scripts or references.
- Prose states the fact, then the reason. No literary phrasing.
- Shipped documents are in English. `docs/chromiumdiff-guide-vi/` is the one
  Vietnamese area.
- A number in prose names the run it was measured on.
- Tests assert code-derived facts, not prose.
