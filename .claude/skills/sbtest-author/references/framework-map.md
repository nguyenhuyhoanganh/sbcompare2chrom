# Framework map

```
run.py                         CLI: --all | --feature a,b | --case ID,ID, --sanity, --reruns, --screenshot-steps
setup.bat                      one-time setup on Windows (venv, requirements, config/local.yaml)
config/
  default.yaml                 settings: attach mode, chrome:// navigation (shown as internet://),
                               args, prefs, timeouts, page paths, report, network
  native_ui.yaml               logical names -> UIA criteria of Samsung's browser UI
                               (verified on Samsung Browser 31), startup_bubbles
  local.yaml                   this machine (git-ignored): browser.exe, proxy
sbtest/
  config.py                    load_config(): default < local < env < CLI; cfg.page_url(name), cfg.display_url(name)
  browser/                     BrowserSession (start/stop/restart), Profile seeding, Chromium
                               version detection, chromedriver resolution/download
  web/                         Selenium layer: locators (CSS, XPath, >>> shadow path, deepcss=, text=,
                               aria=), waits, actions, reader, navigation/tabs/frames/JS dialogs -> `web`
  native/                      pywinauto layer: NativeBrowser (`native`), Dialog, FileDialog, UIA helpers
  pages/
    base.py                    BasePage: Samsung si-* helpers (side bar search, toolbar buttons,
                               snack bar, si-dialog, context menu)
    bookmarks.py history.py downloads.py extensions.py   one page object per internal page
    webstore.py                Chrome Web Store item page (text based)
  data/                        BookmarksSeed, load_data("feature"), files.* generators
  server/local_site.py         LocalSite: resources/site/ + dynamic routes (page, download, upload, auth...)
  reporting/                   evidence (failure files, step screenshots), results.json,
                               confluence_export (folder to upload with the Confluence skill)
  steps.py                     step("N. ...", expected=...) context manager
  pytest_plugin.py             options, markers, fixtures, filters, evidence hooks
  tools/                       doctor, dom, uia_dump, explore, coverage, case_overview, report,
                               confluence_export
tests/
  features/<feature>/          tests, one folder per feature (addons, bookmarks, downloads,
                               history, general); carry @case ids
  framework/                   unit tests of the framework (no browser)
  _scratch/                    throw-away exploration tests (git-ignored)
cases/<feature>/*.md           manual cases with IDs (input); cases/TESTCASES.md overview;
                               cases/_inbox/ raw copies
resources/
  data/                        <name>.yaml test data (bookmark seeds, add-on ids) -> data("name")
  extensions/                  sample_addon/ (unpacked) + sample_addon.crx
  profiles/                    profile templates for @browser(profile=...)
  site/                        local pages: form, inputs, mouse, upload, dialogs, dragdrop, popups,
                               downloads, frames, permissions, toast, shadow, pages/1..3
docs/SETUP.md                  new Windows machine, what to do after a Chromium merge
artifacts/runs/<ts>/           report.html, results.json, junit.xml, failures/, steps/, confluence/
```

## Fixtures

| fixture | what |
|---------|------|
| `web` | `Web` of the current tab: everything inside web content |
| `pages` | page objects: `pages.extensions`, `pages.bookmarks`, `pages.downloads`, `pages.history`, `pages.webstore`; `pages.of(other_web)` |
| `native` | `NativeBrowser`; the test is skipped where native UI cannot work |
| `site` | local web server: `site.page("Title")`, `site.url("/upload.html")`, `site.download("a.txt", 2048)` |
| `session` | `BrowserSession` (`restart()`, `profile`, `driver`, `downloads_dir`) |
| `downloads_dir` | download folder of this profile |
| `data` | `data("addons")` -> `resources/data/addons.yaml` with `{site}` resolved |
| `cfg` | configuration (`cfg.page_url("history")`, `cfg.display_url("history")`) |
| `tmp_path` | pytest temp folder |

## Markers

- `@pytest.mark.case("ADD-001")` - required on product tests; links to the doc
- `@pytest.mark.native` - any step uses `native`
- `@pytest.mark.browser(bookmarks=..., prefs=..., extensions=[...], args=[...], profile=...)`
- `@pytest.mark.sanity`, `@pytest.mark.slow`
- automatic: `addons`/`bookmarks`/... from `tests/features/<feature>/`

## Two layers, one browser

- **web** (Selenium/chromedriver): the DOM of the current tab, including internal pages.
- **native** (pywinauto, UIA): everything else - frame, tab strip, address bar, toolbar, app
  menu and context menus, bubbles/prompts, sign-in and permission prompts, print preview,
  Windows dialogs (Open, Save As, folder), File Explorer, toasts, browser shortcuts, real mouse.

After a native action that changes tabs, sync the web layer (`web.wait_new_tab(before)`).
