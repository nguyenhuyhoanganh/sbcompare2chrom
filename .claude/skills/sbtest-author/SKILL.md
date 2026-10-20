---
name: sbtest-author
description: Turn manual test cases for Samsung Internet for Windows (a Chromium fork) into automated pytest scripts with the sbtest framework (Selenium for web content, pywinauto for native browser UI / OS dialogs). Use when given a list of test cases, test case IDs, or a test doc for bookmarks, history, downloads, settings, add-ons or general browsing, or when asked to add, fix or extend an automated browser test, page object, test data or native dialog handling in this repo.
---

# Writing sbtest scripts from test cases

You receive test cases (a doc, a table, IDs, or prose). You produce: the case in
`testcases/<feature>/*.md`, a passing test in `tests/<feature>/`, and any page-object /
data / config additions it needed. Work case by case; verify each against the real browser.

Read first (short): `references/framework-map.md`. Then open the other references only
when the step needs them:

| Need | Read |
|------|------|
| locators, Shadow DOM, waits, clicks/typing/drag, reading text, tabs, JS dialogs | `references/web-api.md` |
| toolbar/omnibox/menus, bubbles, Save As/Open/Print, OS toasts, shortcuts, real mouse | `references/native-ui.md` |
| preconditions: seeded bookmarks/prefs/extensions, local pages, files, unique values | `references/test-data.md` |
| adding/updating a page object | `references/page-objects.md` |
| feature specifics (bookmarks, history, downloads, settings, add-ons) + known traps | `references/feature-notes.md` |
| test layout, naming, markers, assertions, the template | `references/conventions.md` |
| a test fails / flaky / version mismatch / selector broke after a Chromium merge | `references/debugging.md` |

## Workflow (per test case)

1. **Normalize the case.** Make sure it exists in `testcases/<feature>/<area>.md` in the format
   of `testcases/README.md`, with a unique ID (`BM-`, `HIS-`, `DL-`, `SET-`, `ADD-`, `GEN-`).
   Keep the author's wording of steps and expected results; only add the ID and structure.
   If an ID already exists, never renumber.
2. **Check coverage.** `python -m sbtest.tools.coverage --feature <feature>`: skip cases that
   are already automated unless asked to fix them.
3. **Classify every step** as *web* (inside a tab, including chrome:// pages) or *native*
   (browser frame UI, bubbles, context menus, OS dialogs, keyboard shortcuts handled by
   the browser). Use the mapping table below. A case with any native step gets
   `@pytest.mark.native`.
4. **Plan preconditions as data, not clicks.** Seed bookmarks/prefs/extensions with
   `@pytest.mark.browser(...)` and visit local pages for history. Only the step *under test*
   goes through the UI. See `references/test-data.md`.
5. **Explore the real UI before writing selectors.** Never guess selectors.
   - Web: `python -m sbtest.tools.dom <page> --interactive [--seed-bookmarks f.yaml:key] [--exec "..."]`
     prints every element through shadow roots with a ready locator after `=>`.
   - Native: `python -m sbtest.tools.uia_dump --url ... --keys "^d" --find "(?i)bookmark"`.
6. **Reuse, then extend page objects.** Look in `sbtest/pages/<page>.py` for a method that
   already does the step. If not, add a method (selectors as class constants), not raw
   selectors in the test. New internal page -> new page object + `Pages.REGISTRY`.
7. **Write the test** from `templates/test_template.py`: one test per case, `@pytest.mark.case("ID")`,
   each doc step wrapped in `with step("N. ...", expected="..."):`, assertions = the doc's
   Expected lines. Assert on state (list contents, prefs, files on disk), not on timing.
8. **Run it for real**: `python run.py --case <ID>`, then run it 3 times in a row to prove
   it is stable. Fix until green every time. On failure read `artifacts/runs/<ts>/failures/<test>/`
   (`dom.txt`, `page.png`, `uia.txt`, `screen.png`) before changing code.
9. **Record it**: set `- Automated: tests/...::test_name` under the case in the doc; re-run
   coverage. Report per case: automated / blocked (with the reason and what is needed).

## Step -> API mapping (most common)

| Test case says | Use |
|----------------|-----|
| open bookmark manager / history / downloads / settings / extensions | `pages.bookmarks.open()` ... (`pages.settings.open_section("downloads")`) |
| open a web page | `web.open(site.page("Title"))`, `web.open(site.url("/form.html"))` |
| click / type / select / check in a page | `web.click(loc)`, `web.type(loc, text)`, `web.select(loc, text=..)`, `web.set_checked(loc, True)` |
| item menu (⋮) on a row, Organize menu | page object `item_menu(title, "Edit")`, `organize("Add new folder")` |
| a toast "... deleted" + Undo (in WebUI page) | `page.wait_toast("deleted")`, `page.toast_action("Undo")` |
| dialog inside chrome:// page (Edit bookmark, Remove selected) | `page.open_dialog()`, `page.dialog_input("name")`, `page.dialog_button("Save")` |
| JS alert / confirm / prompt / leave-site | `web.accept_alert(prompt_text=..)`, `web.dismiss_alert()`, `web.alert_text()` |
| press Ctrl+D / Ctrl+H / Ctrl+J / Ctrl+T / Ctrl+Shift+Del | `native.hotkey("^d")` (browser shortcuts never go through `web.press`) |
| press Enter / Esc / Ctrl+A inside a page | `web.press("ENTER")`, `web.press(Keys.CONTROL, "a")` |
| click star / toolbar button / address bar | `native.click("bookmark_star")`, `native.navigate(url)`, `native.omnibox_text()` |
| app menu > Bookmarks > ... | `native.menu("Bookmarks", "Bookmark manager")` |
| right click a link > Open in new tab | `native.context_menu_web(web, loc, "Open link in new tab")` |
| bookmark bubble / "Add extension?" / any browser prompt | `native.wait_dialog("bookmark_added")` -> `.texts()`, `.click("Done")` |
| Save As / Open file / choose folder | `native.file_dialog("save").save_as(path)`, `.open(file)`, `.select_folder(dir)` |
| upload a file via `<input type=file>` | `web.upload(loc, path)` (no OS dialog needed) |
| drag item A onto B in a page | `web.drag_and_drop(a, b, method="html5"|"actions"|"native")` |
| drag a link to the bookmarks bar | `native.drag_web_to_ui(web, loc, "bookmarks_bar")` |
| restart the browser / check persistence | `session.restart()` then rebuild page objects from `session.web` |
| new tab / switch tab / close tab | `web.wait_new_tab(before)`, `web.switch_tab(title=..)`, `web.close_tab()` |
| file downloaded | `web.wait_file(downloads_dir, "name.ext")` |
| verify a setting really changed | `pages.settings.get_pref("download.prompt_for_download")` |
| Windows notification toast | `native.wait_os_toast("(?i)text")` |

## Hard rules

- No `time.sleep` in tests; wait for a condition (`web.wait_*`, `page.wait_*`, `web.wait_until`).
- No internet. Content comes from the local site (`site`) or `test_data/`.
- Tests are independent: any order, any subset, fresh profile by default. Never rely on
  another test's data. Use `unique("Name")` for values the test creates.
- Selectors live in page objects / `config/native_ui.yaml`, not scattered in tests
  (exception: one-off selectors for local test-site pages).
- Native names (Samsung may rename "Bookmark this tab" etc.) go in `config/native_ui.yaml`;
  verify with `uia_dump` on the real Samsung build, never trust upstream Chromium names.
- Internal page URLs come from `cfg.page_url(name)` (config `pages`) - never hardcode `chrome://`
  in tests, the fork may use another scheme.
- Don't weaken an assertion to make a test pass. If the product behaves differently from
  the doc, report it as a possible bug with evidence (paths under `artifacts/`).
- A case you cannot automate (needs real account/sync, hardware, internet) -> leave the
  doc entry, mark it `- Automated: no (reason)` and say so in your report.
