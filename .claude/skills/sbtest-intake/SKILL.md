---
name: sbtest-intake
description: Turns test cases given as a Confluence/Jira link (or pasted text, a table, an export) into normalized Markdown case files under cases/ (one folder per feature) with IDs, ready to automate with sbtest. Use when the user hands over test cases for Samsung Internet sanity testing in any form.
---

# Intake: test cases -> cases/<feature>/*.md

## 1. Get the raw content

- Confluence page / Jira issue link: use the **managing-jira-confluence** skill to read it (include child
  pages or attachments when the user says so). Save the content, as Markdown with tables
  kept, to `cases/_inbox/<page title>.md`, and put the source link on the first line.
- Pasted text / file: save it the same way under `cases/_inbox/`.

`_inbox/` is a raw copy for traceability; tests and coverage never read it.

## 2. Normalize

Write `cases/<feature>/<area>.md` in the format of `cases/README.md`:

- Feature folder: `addons`, `bookmarks`, `downloads`, `history`, `general`
  (a new area -> new folder and prefix; say so in the report).
- **Keep the source IDs** when the doc has them (e.g. `SI-ADD-012`) in the heading. Without
  IDs, assign `<PREFIX>-<next number>` and add `- Source: <link> (section/row)`.
- Steps: numbered, one action each, the author's wording. Expected: one bullet per checkable
  outcome. Preconditions that are data are written as data ("Bookmarks bar contains X").
- `Type:` web / native / mixed (step -> layer table in the `sbtest-author` skill).
- Not automatable (real account, hardware, external apps): `- Automated: no (<reason>)`.
- Never renumber an existing ID.

## 3. Hand over

`python -m sbtest.tools.coverage --feature <feature>` lists what is new. Continue with the
`sbtest-author` skill. Report: cases read, cases written per feature, ambiguities and how
you resolved them, cases marked not automatable.
