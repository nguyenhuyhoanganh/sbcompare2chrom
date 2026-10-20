# Framework map

```
run.py                         CLI: --target samsung|chrome, --suite features|reference|all,
                               --all | --feature a,b | --case ID,ID, --sanity, --reruns, --screenshot-steps
setup.bat                      one-time setup on Windows (venv, requirements, config/local.yaml)
config/
  default.yaml                 common settings (args, prefs, timeouts, page paths, report, network)
  targets/samsung.yaml         attach mode, chrome:// navigation (shown as internet://), Samsung
                               page objects, Samsung native UI map
  targets/chrome.yaml          chrome:// scheme, Chromium page objects, Chromium native UI map
  native_ui/chromium.yaml      logical names -> UIA criteria (upstream Chrome UI)
  native_ui/samsung.yaml       same for Samsung (verified on Samsung Browser 31), startup_bubbles
  local.yaml                   this machine (git-ignored): exe paths per target, proxy
sbtest/
  config.py                    load_config(): default < target < local < env < CLI; cfg.page_url(name)
  browser/                     BrowserSession (start/stop/restart), Profile seeding, Chromium
                               version detection, chromedriver resolution/download
  web/                         Selenium layer: locators (CSS, XPath, >>> shadow path, deepcss=, text=,
                               aria=), waits, actions, reader, navigation/tabs/frames/JS dialogs -> `web`
  native/                      pywinauto layer: NativeBrowser (`native`), Dialog, FileDialog, UIA helpers
  pages/
    base.py                    BasePage: shared WebUI helpers (search, toast, cr-dialog, menus)
    chromium/                  verified page objects for upstream chrome:// pages (reference)
    samsung/                   Samsung page objects (subclass chromium/, override what differs)
    webstore.py                Chrome Web Store item page (text based)
  data/                        BookmarksSeed, load_data("feature"), files.* generators
  server/local_site.py         LocalSite: test_site/ + dynamic routes (page, download, upload, auth...)
  reporting/                   evidence (failure files, step screenshots), results.json,
                               confluence_export (folder to upload with the Confluence skill)
  steps.py                     step("N. ...", expected=...) context manager
  pytest_plugin.py             options, markers, fixtures, filters, evidence hooks
  tools/                       doctor, dom, uia_dump, coverage, get_chrome, confluence_export
test_site/                     local pages: form, inputs, mouse, upload, dialogs, dragdrop, popups,
                               downloads, frames, permissions, toast, shadow, pages/1..3
test_data/                     <feature>.yaml data, extensions/ (sample_addon + .crx), profiles/
testcases/<feature>/*.md       manual cases with IDs (input); testcases/_inbox/ raw copies
tests/
  features/<feature>/          product tests, one folder per feature (addons, bookmarks,
                               downloads, history, settings, general); carry @case ids
  reference/web|files|native/  interaction catalogue on Chrome (see tests/reference/README.md)
framework_tests/               unit tests of the framework (no browser)
artifacts/runs/<ts>/           report.html, results.json, junit.xml, failures/, steps/, confluence/
```

## Fixtures

| fixture | what |
|---------|------|
| `web` | `Web` of the current tab: everything inside web content |
| `pages` | page objects of the current target: `pages.extensions`, `pages.bookmarks`, `pages.downloads`, `pages.history`, `pages.settings`, `pages.webstore`; `pages.of(other_web)` |
| `native` | `NativeBrowser`; the test is skipped where native UI cannot work |
| `site` | local web server: `site.page("Title")`, `site.url("/upload.html")`, `site.download("a.txt", 2048)` |
| `session` | `BrowserSession` (`restart()`, `profile`, `driver`, `downloads_dir`) |
| `downloads_dir` | download folder of this profile |
| `data` | `data("addons")` -> `test_data/addons.yaml` with `{site}` resolved |
| `cfg` | configuration (`cfg.target`, `cfg.page_url("history")`) |
| `tmp_path` | pytest temp folder |

## Markers

- `@pytest.mark.case("ADD-001")` - required on product tests; links to the doc
- `@pytest.mark.native` - any step uses `native`
- `@pytest.mark.browser(bookmarks=..., prefs=..., extensions=[...], args=[...], profile=...)`
- `@pytest.mark.sanity`, `@pytest.mark.slow`
- automatic: `addons`/`bookmarks`/... from `tests/features/<feature>/`, `reference` from `tests/reference/`

## Two layers, one browser

- **web** (Selenium/chromedriver): the DOM of the current tab, including internal pages.
- **native** (pywinauto, UIA): everything else - frame, tab strip, address bar, toolbar, app
  menu and context menus, bubbles/prompts, sign-in and permission prompts, print preview,
  Windows dialogs (Open, Save As, folder), File Explorer, toasts, browser shortcuts, real mouse.

After a native action that changes tabs, sync the web layer (`web.wait_new_tab(before)`).
