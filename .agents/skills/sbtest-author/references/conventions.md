# Conventions

## Files and names

- Tests: `tests/features/<feature>/test_<feature>_<area>.py` - feature = folder (`addons`,
  `bookmarks`, `downloads`, `history`, `general`). New feature area (e.g. `settings`) -> new
  folder + `FEATURES` in `sbtest/pytest_plugin.py` + `cases/<feature>/` + a row in
  `FEATURES` of `sbtest/tools/case_overview.py`.
- Native-only cases may live in `test_<area>_native.py` or in the same file with
  `@pytest.mark.native`; either is fine, be consistent within a feature.
- Test name: `test_<what_it_verifies>` in snake case (`test_delete_and_undo`), not the ID.
- One test function per case ID. A case may get extra helper tests without IDs only for
  framework behaviour; product checks always carry an ID.
- Module docstring: what area + `Cases: cases/<feature>/<file>.md`.

## Test shape

```python
@pytest.mark.case("BM-004")
@pytest.mark.browser(bookmarks="seed_basic")      # preconditions
def test_delete_and_undo(pages):
    bm = pages.bookmarks
    with step("1. Open the bookmark manager"):
        bm.open()
    with step("2. Delete 'Static page 2'", expected="item gone + toast"):
        toast = bm.delete("Static page 2")
    assert "deleted" in toast.lower()
    with step("3. Undo", expected="item is back"):
        bm.undo()
        bm.wait_item("Static page 2")
```

- Step titles start with the doc's step number(s): `"2-3. ..."` when merged.
- `expected=` copies the doc's expected result for that step (shown in the report on failure).
- Assertions: plain `assert` with a clear left side; for "eventually" conditions use a
  `wait_*` (it raises with a message) instead of `assert` + retry loops.
- Check the *result*, not just that the click happened: list content, pref value,
  file on disk, URL/title, text of the toast.
- Keep each test < ~60 s; mark longer ones `@pytest.mark.slow`.
- No cleanup needed for browser data: each test has its own profile. Clean only things
  outside the profile you created (files outside `tmp_path`/`downloads_dir`, windows of
  other apps).

## Imports used by tests

```python
import pytest
from sbtest.steps import step
from sbtest.utils import unique
from sbtest.data import files                      # generated files
from sbtest.web import Keys                       # web.press(Keys.CONTROL, "a")
```

## Doc update

Under the case in `cases/<feature>/<file>.md` set
`- Automated: tests/features/<feature>/test_x.py::test_name` (or `no (<reason>)`).

## Before you finish

- `python run.py --case <IDs>` green 4x in a row on the real build.
- `python -m pytest tests/framework -q` green if you touched `sbtest/`.
- `python -m sbtest.tools.coverage --feature <feature>` shows the IDs as OK.
