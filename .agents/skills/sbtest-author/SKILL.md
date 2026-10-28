---
name: sbtest-author
description: Turns manual test cases for Samsung Internet for Windows (a Chromium fork) into automated pytest scripts with the sbtest framework (Selenium for web content, pywinauto for browser UI and Windows dialogs). Use when given test cases or case IDs for add-ons, bookmarks, downloads, history, settings or general browsing, or when asked to add, fix or extend a test, a page object, test data or native UI handling in this repo.
---

# Writing sbtest scripts from test cases

You work on the Windows machine with the Samsung Internet build: launch the browser with the
tools, look at screenshots and dumps, and iterate until the test passes.

- **Working method + action table** (request -> call for every page, toolbar, bubble,
  dialog): the `sbtest-explore` skill. Follow its checklist per case; this skill is the
  framework reference it points to.
- Raw links or docs instead of cases -> the `sbtest-intake` skill first.
- Existing tests in `tests/features/` are runnable examples of every interaction
  (toolbar, bubbles, Save As / Open / folder dialogs, Explorer, add-on popups, context menus).

Read `references/framework-map.md` first, then only what the step needs:

| Need | Read |
|------|------|
| locators, Shadow DOM, waits, clicks/typing/drag, reading text, tabs, frames, JS dialogs | `references/web-api.md` |
| toolbar/omnibox/menus, bubbles/prompts, Save As/Open/folder, Explorer, toasts, shortcuts | `references/native-ui.md` |
| preconditions: seeded bookmarks/prefs/add-ons, local pages, files, unique values | `references/test-data.md` |
| adding or adapting a page object | `references/page-objects.md` |
| feature specifics and traps (add-ons, bookmarks, downloads, history) - before every step | `references/feature-notes.md` |
| layout, naming, markers, assertions, template | `references/conventions.md` |
| a test fails / is flaky / a selector broke after a Chromium merge | `references/debugging.md` |

**web or native?** Inside the page (internal pages too) -> `web` / page objects. Browser
frame, toolbar, address bar, menus, bubbles, shortcuts (Ctrl+D/H/J...), Windows dialogs,
Explorer, real mouse -> `native`, and mark the test `@pytest.mark.native`.

## Hard rules

- Preconditions as data (`@pytest.mark.browser(bookmarks=..., prefs=..., extensions=[...])`,
  visited local pages); only the step under test goes through the UI.
- No `time.sleep`; wait for a condition (`web.wait_*`, page `wait_*`, `web.wait_until`).
- No internet except the Web Store case. Content comes from `site` / `resources/data/`.
- Tests are independent (any order, any subset, fresh profile). Use `unique("Name")`.
- No selectors, URLs (`internet://`), machine paths or native UI names in tests: page
  objects, `config/default.yaml`, `config/native_ui.yaml`, `config/local.yaml`.
- Never weaken an assertion to pass. Product differs from the doc -> report it with the
  evidence paths.
- Not automatable -> `- Automated: no (<reason>)` in the doc and in your report.
