# sbtest

Automated sanity tests for Samsung Internet (Samsung Browser) for Windows, a Chromium fork.
Selenium drives web content and internal pages, pywinauto drives the browser UI and Windows
dialogs. Each run produces a per-build report (HTML, Markdown, Confluence page).

## Requirements

- Windows 10/11, an unlocked desktop (native tests use the real mouse and keyboard)
- Python 3.10+ (3.12+ recommended: its pip trusts the Windows certificate store)
- The Samsung Browser build to test (`SamsungInternet.exe`)
- Internet on first setup (packages, chromedriver); behind a proxy set `HTTPS_PROXY`
- A short repo folder such as `C:\sbtest` (browser profile paths are limited to 260 characters)

## Setup

```bat
.\setup.bat                                          & rem exe from config\local.yaml, asked the first time
.\setup.bat --exe "C:\build\SamsungInternet.exe"     & rem check a given build
```

Installs the packages into `.venv`, then checks the machine: keyboard, Chromium version,
chromedriver (downloaded when missing), browser start, internal pages, toolbar. It ends with
`READY` or `NOT READY`; every `[FAIL]` line has a `fix:` line. Re-check only:
`.venv\Scripts\python -m sbtest.tools.doctor`.

## Run

```bat
.venv\Scripts\python run.py --sanity                  & rem quick pass
.venv\Scripts\python run.py --all                     & rem every test, about 8-10 minutes
.venv\Scripts\python run.py --feature bookmarks       & rem addons, bookmarks, downloads, history, general
.venv\Scripts\python run.py --case BM-114,DL-003
.venv\Scripts\python run.py --list                    & rem cases and automation status
```

Add `--exe "<path>"` when setup used it. Other options: `--no-native` (skip tests that drive
the real UI), `--reruns 1`, `--record` (a video of every test: browser windows, the running
case step as a caption, clicks and typing framed in red), `--screenshot-steps` (the same as
pictures: one before every click / typing, plus one per step), `--min-step 1` (every test step
lasts at least 1 s; default 0.5 s, `0` = no pause), `--raw` (pytest's own output).

While tests run: keep hands off the mouse and keyboard, keep the keyboard on English (US) with
Vietnamese input tools in English mode, and keep the screen unlocked.

## Results

`artifacts\test-results\` holds the latest run only:

- `report\index.html` - verdict BUILD PASSED / FAILED, one row per case with steps, expected,
  result and screenshot
- `confluence\` - the same report as a Confluence page with attachments; with `--record` /
  `--screenshot-steps` it also carries the videos / step pictures of failed cases in a
  collapsed block per case (`--confluence-steps all` for every case, `none` for none)
- `videos\<test>.mp4` - `--record` videos (also played in the report)
- `failures\<test>\` - `failure.txt`, screenshots, DOM and UI Automation dumps

Case overview with the latest results: `python -m sbtest.tools.case_overview` -> `tests\features\TESTCASES.md`.

## New Chromium merge

Run `setup.bat` with the new exe: chromedriver follows the build's Chromium version
automatically. Then `run.py --all`; a test that fails because labels or markup changed is fixed
in the page object (`sbtest\pages\`) or `config\native_ui.yaml`, not in the test.

## Layout

```
config/          settings: default.yaml, native_ui.yaml (browser UI names), local.yaml (this machine)
sbtest/          framework: browser, web, native, pages, reporting, tools
tests/features/  one folder per feature: case docs (*.md) + their tests; TESTCASES.md overview
tests/framework/ self-tests without a browser: python -m pytest tests/framework -q
resources/       test data, sample add-on, profile templates, local test site
artifacts/       output of runs and tools, downloaded chromedriver (git-ignored)
AGENTS.md        rules for coding agents
.agents/skills/  agent skills (Agent Skills format)
```

## Agents

Agents that support `AGENTS.md` and Agent Skills load the rules and the skills from this repo:
`sbtest` (guided build check: scope, exe, run, triage, Confluence page), `sbtest-run`,
`sbtest-explore`, `sbtest-author`, `sbtest-intake`. Agents without skill support: ask them to
read `AGENTS.md` first.
