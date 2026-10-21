# Test case documents (input for test authors / agents)

Overview of every case (counts, type, sanity flag, last result): `TESTCASES.md`.

Product test cases for Samsung Internet. Raw copies of source documents (Confluence pages,
exports) go to `_inbox/`; the normalized cases below are what tests and coverage use.
Put one markdown file per feature area (or per doc you receive) under the matching folder:

```
cases/
  addons/   bookmarks/   downloads/   history/   general/
```

Convert any source doc (Excel, Word, Confluence...) into this format. Each case **must** have
a unique ID with the feature prefix; the automated test carries the same ID via
`@pytest.mark.case("BM-001")` (tests in `tests/features/<feature>/`), so coverage can be tracked and a single case can be run
with `python run.py --case BM-001`.

| Feature    | Prefix | Folder              |
|------------|--------|---------------------|
| Bookmarks  | BM     | cases/bookmarks |
| History    | HIS    | cases/history   |
| Downloads  | DL     | cases/downloads |
| Settings   | SET    | (none yet - reserved prefix) |
| Add-ons    | ADD    | cases/addons    |
| General    | GEN    | cases/general   |

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
