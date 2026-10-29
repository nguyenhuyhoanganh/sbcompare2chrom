---
name: sbtest-intake
description: Turns test cases given as a Confluence/Jira link (or pasted text, a table, an export) into normalized Markdown case files in tests/features (one folder per feature, next to its tests) with IDs, ready to automate with sbtest. Use when the user hands over test cases for Samsung Internet sanity testing in any form.
---

# Intake: test cases -> tests/features/<feature>/*.md

## 1. Get the raw content

- Confluence page / Jira issue link: use the **managing-jira-confluence** skill to read it (include child
  pages or attachments when the user says so). Save the content, as Markdown with tables
  kept, to `tests/features/_inbox/<page title>.md`, and put the source link on the first line.
- Pasted text / file: save it the same way under `tests/features/_inbox/`.

`_inbox/` is a raw copy for traceability; tests and coverage never read it.

## 2. Normalize

Write `tests/features/<feature>/<area>.md` in the format of `tests/features/README.md`:

- Feature folder: `addons`, `bookmarks`, `downloads`, `history`, `general`
  (a new area -> new folder and prefix; say so in the report).
- **Use the IDs the source gives** (the team's own scheme, e.g. `SI-ADD-012`) in the heading,
  and add `- Source: <link> (section/row)`. A case without an ID: ask the user for it - never
  invent one.
- Steps: numbered, one action each, the author's wording. Expected: one bullet per checkable
  outcome. Preconditions that are data are written as data ("Bookmarks bar contains X").
- `Type:` web (only page content) / native (browser toolbar, menus, bubbles, shortcuts,
  Windows dialogs) / mixed - see "web or native?" in the `sbtest-author` skill.
- Not automatable (real account, hardware, external apps): `- Automated: no (<reason>)`.
- Never renumber or change an existing ID.

## 3. Hand over

`python -m sbtest.tools.coverage --feature <feature>` lists which cases have no test yet. Automate them with the `sbtest-explore` skill (working method), one case at a time. Report: cases read, cases written per feature, ambiguities and how
you resolved them, cases marked not automatable.
