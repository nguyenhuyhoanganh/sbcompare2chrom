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
   not against its name.
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
   pair it came from or come from `docs/figures.json`.

Two more, cheap to avoid: write where a field *is* rather than what does not
exist, and do not state a prohibition the code does not enforce.

## Elsewhere

- Prose states the fact, then the reason. No literary phrasing.
- Shipped documents are in English. `docs/chromiumdiff-guide-vi/` is the one
  Vietnamese area.
- A number in prose either names the run it was measured on or comes from
  `docs/figures.json`.
- Tests assert code-derived facts, not prose.
