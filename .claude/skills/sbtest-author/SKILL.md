---
name: sbtest-author
description: Turn manual test cases for Samsung Internet for Windows (a Chromium fork) into automated pytest scripts with the sbtest framework (Selenium for web content, pywinauto for browser UI and Windows dialogs). Use when given test cases or case IDs for add-ons, bookmarks, downloads, history, settings or general browsing, or when asked to add, fix or extend a test, a page object, test data or native UI handling in this repo.
---

# Writing sbtest scripts from test cases

**Where you work:** on the Windows machine with the Samsung Internet build (Samsung Internet
is Windows-only). Launch the browser yourself with the tools below, look at screenshots and
dumps, and iterate until the test passes.

**Two targets, one code base.** `--target samsung` (the product) and `--target chrome`
(Chrome for Testing, same Chromium base). Tests in `tests/features/` run on both; the
`pages` fixture picks `sbtest/pages/samsung/` or `sbtest/pages/chromium/` by target.

**Samsung rewrote many internal pages** (`internet://extensions`, `internet://bookmarks` ...).
`sbtest/pages/samsung/*` start as subclasses of the verified Chromium page objects. The first
time a test touches a Samsung page: explore it on the build, then override the selectors /
methods that differ in the Samsung class and update its STATUS docstring. Keep the parent's
method names and return types.

**Need an interaction you have not done before?** Find it in `tests/reference/README.md`
(upload via Open dialog, Save As, folder picker, Explorer drag, prompts, print, shortcuts,
menus, iframes, JS dialogs ...) - working examples on Chrome - and copy the pattern.

If the user gives links or raw docs instead of cases, run the `sbtest-intake` skill first.

Read first: `references/framework-map.md`. Then only what the step needs:

| Need | Read |
|------|------|
| locators, Shadow DOM, waits, clicks/typing/drag, reading text, tabs, frames, JS dialogs | `references/web-api.md` |
| toolbar/omnibox/menus, bubbles/prompts, Save As/Open/folder, Explorer, toasts, shortcuts | `references/native-ui.md` |
| preconditions: seeded bookmarks/prefs/add-ons, local pages, files, unique values | `references/test-data.md` |
| adding or adapting a page object (Chromium vs Samsung) | `references/page-objects.md` |
| feature specifics and traps (add-ons, bookmarks, downloads, history, settings) | `references/feature-notes.md` |
| layout, naming, markers, assertions, template | `references/conventions.md` |
| a test fails / is flaky / a selector broke after a Chromium merge | `references/debugging.md` |

## Workflow (per test case)

1. **Case doc.** It exists in `testcases/<feature>/<area>.md` with an ID (else `sbtest-intake`).
2. **Coverage.** `python -m sbtest.tools.coverage --feature <feature>`; skip automated ones
   unless asked to fix them.
3. **Classify each step** web or native (table below). Any native step -> `@pytest.mark.native`.
4. **Preconditions as data**: `@pytest.mark.browser(bookmarks=..., prefs=..., extensions=[...])`,
   visit local pages for history. Only the step under test goes through the UI.
5. **Explore, never guess selectors**:
   `python -m sbtest.tools.dom <page> --interactive [--exec "..."]` (DOM through shadow roots,
   each line ends with a ready locator) and `python -m sbtest.tools.uia_dump --find "(?i)..."`
   (native UI). Compare with `--target chrome` to see what Samsung changed.
6. **Page object first**: reuse a method; else add it to the Samsung class (and to the Chromium
   class too when the behaviour is generic). Selectors are class constants, never in tests.
7. **Write the test** in `tests/features/<feature>/test_<area>.py` from
   `templates/test_template.py`: `@pytest.mark.case("ID")`, each doc step in
   `with step("N. ...", expected="..."):`, assertions = the doc's Expected lines, on state.
8. **Run for real**: `python run.py --case <ID>`, then 3 more times - green every time. On a
   failure read `artifacts/runs/<ts>/failures/<test>/failure.txt`, then `page.png` (the
   element used is outlined red) and `screen.png` (whole screen). `--screenshot-steps` shows
   every step. If it is generic, check it on `--target chrome` too.
9. **Record**: `- Automated: tests/features/...::test_name` under the case; re-run coverage.
   Report per case: automated / blocked (reason, what is needed).

## Step -> API mapping

| Test case says | Use |
|----------------|-----|
| open add-ons / bookmarks / history / downloads / settings | `pages.extensions.open()` ... `pages.settings.open_section("downloads")` |
| open a web page | `web.open(site.page("Title"))`, `web.open(site.url("/form.html"))` |
| click / type / select / check | `web.click(loc)`, `web.type(loc, text)`, `web.select(loc, text=..)`, `web.set_checked(loc, True)` |
| row menu (⋮), toolbar menu | page object `item_menu(title, "Edit")`, `organize("Add new folder")` |
| toast "... deleted" + Undo (internal page) | `page.wait_toast("deleted")`, `page.toast_action("Undo")` |
| dialog inside an internal page | `page.open_dialog()`, `page.dialog_input("name")`, `page.dialog_button("Save")` |
| JS alert / confirm / prompt | `web.accept_alert(prompt_text=..)`, `web.dismiss_alert()`; navigation behind a browser prompt: `web.open(url, blocking=False)` |
| "Leave site?" (beforeunload) | not observable: chromedriver accepts it automatically -> `Automated: no (WebDriver auto-accepts beforeunload)` |
| iframe content | `with web.frame("#frame"): ...` |
| Ctrl+D / Ctrl+H / Ctrl+J / Ctrl+T / Ctrl+W / Ctrl+L | `native.hotkey("^d")` (never `web.press`) |
| Enter / Esc / Ctrl+A inside a page | `web.press("ENTER")`, `web.press(Keys.CONTROL, "a")` |
| star / back / reload / new tab button / address bar | `native.click("bookmark_star")`, `native.navigate(url)`, `native.omnibox_text()` |
| app menu > X > Y | `native.menu("X", "Y")` |
| right click > menu item | `native.context_menu_web(web, loc, "Open link in new tab")` |
| bubble / prompt / permission / sign-in dialog | `native.wait_dialog("bookmark_added")` -> `.texts()`, `.set_text(..)`, `.click("Done")`, `.click_any("Allow", ..)` |
| upload through a button (Open dialog) | `web.click(button)` then `native.file_dialog("open").open(f1, f2)` |
| upload through `<input type=file>` | `web.upload(loc, path)` |
| Save As / save page / download with "ask where" | `native.file_dialog("save").save_as(path)` |
| choose a folder | `native.file_dialog("open").select_folder(dir)` |
| drag a file from File Explorer | `native.drag_file_from_explorer(path, web=web, target=loc)` |
| "Show in folder" | `native.wait_explorer(folder)`, `native.explorer_selected(win)` |
| install add-on: unpacked / .crx / Web Store | `pages.extensions.load_unpacked(native, dir)`, `.drop_crx(native, crx)`, `pages.webstore.install(id, native)` |
| drag & drop in a page | `web.drag_and_drop(a, b, method="html5"|"actions"|"native")` |
| restart browser, check persistence | `session.restart()`; then `pages.of(session.web)` |
| tabs | `before = web.tabs` ... `web.wait_new_tab(before)`, `web.switch_tab(title=..)`, `web.close_tab()` |
| file downloaded | `web.wait_file(downloads_dir, "name.ext")` |
| print preview | `native.wait_dialog("print")` -> `.click_any("Cancel")` |
| Windows notification | `native.wait_os_toast("(?i)text")` |

## Hard rules

- No `time.sleep`; wait for a condition (`web.wait_*`, page `wait_*`, `web.wait_until`).
- No internet except the Web Store case. Content comes from `site` / `test_data/`.
- Tests are independent (any order, any subset, fresh profile). Use `unique("Name")`.
- No selectors, URLs (`internet://`), machine paths or native UI names in tests: page
  objects, `config/targets/*.yaml`, `config/native_ui/*.yaml`, `config/local.yaml`.
- Never weaken an assertion to pass. Product differs from the doc -> report it with the
  evidence paths.
- Not automatable -> `- Automated: no (<reason>)` in the doc and in your report.
