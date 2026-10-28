# Debugging failing / flaky tests

## Evidence first

Every failed test writes `artifacts/test-results/failures/<test id>/` (latest run only):

| file | content |
|------|---------|
| `failure.txt` | test, case ids, failed step, expected, error, last element used (+ NOT FOUND), url - read first |
| `page.png` | screenshot of the tab, the last element the test used outlined in red |
| `dom.txt` | URL, title, tab count + full shadow-piercing DOM dump with locators |
| `page.html` | light DOM page source |
| `alert.txt` | text of an open JS dialog (when one blocked everything) |
| `screen.png` | the browser's windows as on screen: frame + native dialogs/bubbles/prompts/menus (other apps and monitors left out; `report.screen_capture: screen` for every monitor, e.g. to see File Explorer) |
| `uia.txt` | UIA tree of all browser windows - Windows |

`--screenshot-steps` (run.py or pytest) also writes `steps/<test>/NN_<status>_<step>.png`
(+ `_screen.png`) after every `step()`. `results.json` holds every test's outcome, steps
and evidence paths (used by the Confluence report).

The pytest output also has a `sbtest steps` section (which doc step failed) and the
chromedriver log is in `artifacts/test-results/logs/`. Read these before editing code.

## Typical failures

| Symptom | Likely cause / fix |
|---------|--------------------|
| `Timed out ... element visible <loc>` | selector changed (diff `dom.txt` vs page object), element hidden (collapsed tree, closed menu), or wrong frame/tab |
| works alone, fails in a run | shared state: use `unique()` names, don't depend on order, avoid `--browser-scope session` for this test (add a `browser()` marker) |
| `StaleElementReferenceException` | list re-rendered: re-find inside the wait, read rows in one JS call |
| `ElementClickInterceptedException` | overlay/toast/menu over it: wait for it to close; `web.click` already falls back to JS click |
| native dialog not found | different title in Samsung build -> `uia_dump --find`, fix `config/native_ui.yaml`; window not foreground (RDP/lock screen) |
| typing into cr-input does nothing | target the inner `>>> input` |
| `chromedriver ... is version X but the browser is Chromium Y` | wrong driver in `drivers/<major>/` (delete the folder, it is downloaded again) or a pinned `browser.chromedriver` |
| detected Chromium = the Samsung product version (31.x) | the build puts its product version in DevTools `Browser`; `chromium_version_from` then uses the User-Agent `Chrome/N.0.0.0` - check the `DevTools /json/version` log line, or pin `browser.chromium_version` |
| `unrecognized Chrome version` / `cannot parse ... Browser` with Google's chromedriver | the fork reports a non-Chrome product name in DevTools `/json/version`: use a chromedriver built from the fork (`browser.chromedriver`) |
| chromedriver download fails | it uses Windows' `curl.exe` (Windows certificate store, so company TLS inspection is fine; urllib only as fallback): read the `curl exit N` line; proxy: set `HTTPS_PROXY` or `network.download_proxy`; or copy the driver to `drivers/<major>/chromedriver.exe` |
| `X did not render at ... expected internet://...` | wrong `pages.scheme`/path, or the page object's ROOT no longer matches the rewritten page |
| browser starts but chromedriver can't connect | try `--mode attach`; check that the fork keeps `--remote-debugging-port` and reports `Chrome/x.y.z.w` in `/json/version` |
| `invalid session id ... Unable to receive message from renderer` | browser/renderer crashed: real bug (save the log!) or an unstable machine; re-run once to tell them apart |
| page objects fail right after `session.restart()` | they hold the old `web`: rebuild from `session.web` |

## Interactive exploration

```
python -m sbtest.tools.dom <page> --interactive --exec "<python using web/site/session>"
python -m sbtest.tools.uia_dump --url <page> --keys "^d" --find "(?i)done"
python run.py --case BM-004 --keep-profile -- -x -s --log-cli-level=INFO
```

`--keep-profile` leaves `artifacts/test-results/profiles/<test>_xxxx` - open it with the exe
(`SamsungInternet.exe --user-data-dir=<dir>`) to look at the state by hand.

## After a Chromium merge

1. Run `python run.py --all --reruns 1` on the new build.
2. Group failures by page object; most breakages are renamed ids/tags in WebUI.
3. For each: `dom` tool on the page, update selector constants, re-run that feature.
4. Native: `uia_dump` and update `config/native_ui.yaml`.
5. A failure that is real product behaviour change -> report, don't "fix" the test.
