# Framework map

```
run.py                     CLI: --exe, --all | --feature a,b | --case ID,ID, --sanity, --headless, --reruns
config/default.yaml        all settings (exe, driver, args, prefs, timeouts, internal page URLs, native)
config/local.yaml          machine settings (git-ignored), copy from local.example.yaml
config/native_ui.yaml      logical names -> UIA criteria for browser UI and dialogs
sbtest/
  config.py                load_config(); cfg.get("a.b"), cfg.page_url("bookmarks"), cfg.native_enabled
  browser/session.py       BrowserSession: start/stop/restart, .web, .native, .profile, .downloads_dir
  browser/profile.py       fresh user-data-dir; .prefs({...}) .bookmarks(seed) .copy_from(dir)
  browser/version.py       detect Chromium version of the exe (DevTools /json/version), cached
  browser/driver_resolver  chromedriver: config -> drivers/<major>/ -> Selenium Manager download
  core/locators.py         locator syntax (css, xpath, ">>>" shadow path, deepcss=, text=, aria=)
  core/web.py              Web = waits + actions + reader + navigation (one object: `web`)
  native/browser_ui.py     NativeBrowser (`native`): hotkeys, toolbar, menus, dialogs, mouse, dump
  native/dialogs.py        Dialog (generic native window), FileDialog (Save As/Open/folder)
  native/uia.py            UIA search/dump helpers
  pages/                   page objects: bookmarks, history, downloads, settings, extensions, webstore
                           (written against upstream Chromium - re-verify on the Samsung build)
  atlassian.py             Confluence/Jira Server/DC client (PAT) + storage->Markdown
  data/                    BookmarksSeed, load_data("feature"), files.* generators
  server/local_site.py     LocalSite: static test_site/ + /page /download /slow-download /echo ...
  steps.py                 step("N. ...", expected=...) context manager
  pytest_plugin.py         fixtures, markers, --feature/--case filters, failure evidence
  tools/dom.py             DOM explorer through shadow roots (prints locators)
  tools/uia_dump.py        native UIA explorer (Windows)
  tools/coverage.py        doc case ids vs automated tests
  tools/atlassian_read.py  Confluence/Jira link -> testcases/_inbox/*.md
  tools/confluence_report  results.json -> new Confluence page with failure screenshots
test_site/                 local pages: form, dialogs, dragdrop, popups, downloads, toast, shadow, pages/1..3
test_data/                 <feature>.yaml data, extensions/sample_addon, profiles/<template>
testcases/<feature>/*.md   the manual cases (input), with IDs
tests/<feature>/test_*.py  automated tests; folder name = feature marker
framework_tests/           unit tests of the framework itself (no browser needed)
artifacts/                 runs/<ts>/report.html, junit.xml, results.json, failures/<test>/...,
                           steps/<test>/ (with --screenshot-steps), profiles, logs
```

## Fixtures (ask for them by name in the test signature)

| fixture | what |
|---------|------|
| `web` | `Web` for the current tab: everything inside web content |
| `pages` | `pages.bookmarks`, `pages.history`, `pages.downloads`, `pages.settings`, `pages.extensions` |
| `native` | `NativeBrowser` - test is skipped automatically where native UI is unavailable |
| `site` | local web server: `site.page("Title")`, `site.url("/form.html")`, `site.download("a.txt", 2048)` |
| `session` | `BrowserSession` (`restart()`, `profile`, `driver`) |
| `downloads_dir` | the download folder of this browser profile |
| `data` | `data("bookmarks")` -> `test_data/bookmarks.yaml` with `{site}` resolved |
| `cfg` | configuration |
| `tmp_path` | pytest temp dir (files to upload, Save As targets) |

## Markers

- `@pytest.mark.case("BM-001")` - required, links to the doc (`--case` filter, coverage)
- `@pytest.mark.native` - any step uses `native`
- `@pytest.mark.browser(bookmarks=..., prefs=..., extensions=[...], args=[...], profile=...)` - preconditions
- `@pytest.mark.sanity` - include in the quick pass (`run.py --sanity`)
- `@pytest.mark.slow` - long (> ~20 s)
- feature markers are automatic from the folder (`tests/history/...` -> `history`)

## Two layers, one browser

- **Web layer (Selenium/chromedriver)**: DOM of the current tab, including chrome:// WebUI
  pages (bookmarks, history, downloads, settings, extensions are web pages with Shadow DOM).
- **Native layer (pywinauto, UIA backend)**: what is *not* DOM - window frame, tab strip,
  omnibox, toolbar buttons, app menu and context menus, bubbles/prompts (bookmark added,
  add extension, download bubble, permission prompts), OS dialogs (Save As, Open, Print),
  OS toasts, browser shortcuts, real mouse. Windows only; skipped headless / on Linux.

Both act on the same browser process. After a native action that changes tabs, sync the
web layer: `web.wait_new_tab(before)` or `web.switch_tab(title=...)`.
