# Features: test case documents + their tests

Overview of every case (counts, type, sanity flag, last result): `TESTCASES.md`.

Product test cases for Samsung Internet. Raw copies of source documents (Confluence pages,
exports) go to `_inbox/`; the normalized cases below are what tests and coverage use.
Each feature folder holds its case docs (one markdown file per area or per doc you receive)
next to the tests that automate them:

```
tests/features/
  addons/   bookmarks/   downloads/   history/   general/
    sanity.md  toolbar.md  <area>.md      case docs
    test_<feature>_<area>.py              tests
```

Convert any source doc (Excel, Word, Confluence...) into this format. Each case **must** have
a unique ID; the automated test carries the same ID via `@pytest.mark.case("BM-001")`, so
coverage can be tracked and a single case can be run with `python run.py --case BM-001`.

Folders: `addons/`, `bookmarks/`, `downloads/`, `general/`, `history/` (the IDs used so far start
with ADD, BM, DL, GEN, HIS).

IDs are given by the team with each case (their own scheme): use them as they are, never
invent, renumber or change one. A case without an ID -> ask for it. An ID is letter/digit groups
joined by `-` and ending in a number (`BM-001`, `SI-ADD-012`), unique across all features.

## Format

```markdown
## BM-001 Add a bookmark from the bookmark manager
- Priority: High
- Type: web | native | mixed          (optional hint: does it touch browser UI / OS dialogs?)
- Precondition: Clean profile; local page "Static page 1" exists
- Steps:
  1. Open the bookmark manager
  2. Open the Organize menu and choose "Add new bookmark"
  3. Enter name "My new bookmark" and the URL, click Save
- Expected:
  - The bookmark "My new bookmark" is listed in Bookmarks bar
- Automated: tests/features/bookmarks/test_bookmark_manager.py::test_add_bookmark   (filled in when automated)
```

`python -m sbtest.tools.coverage` lists which IDs are automated, missing, or orphaned.
