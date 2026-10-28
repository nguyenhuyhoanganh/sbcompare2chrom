---
name: sbtest-run
description: Runs the Samsung Internet automated tests (all, by feature, or by test case id) against a build, triages the failures and publishes the run report to Confluence. Use when asked to run/execute the tests, check a new build after a Chromium merge, re-run failures, explain failures, or share results.
---

# Run, triage, report

Copy this checklist into your reply and tick it off:

```
- [ ] setup.bat READY (new machine / new build)
- [ ] tests run (selection noted)
- [ ] every failure in one triage bucket, buckets 2-4 fixed and re-run
- [ ] report published (if asked) and verdict + triage table + link sent
```

New machine or new build: `.\setup.bat --exe "<path>"` must end with READY.
`python` below = `.venv\Scripts\python.exe`, created by setup.bat; how to call both from
PowerShell / cmd / Git Bash: the `sbtest` skill, top. `--all` takes 8-10 minutes: run it in
the background or with a timeout of at least 20 minutes.

## Run

```
python run.py --all                                # every feature (tests/features)
python run.py --feature addons,bookmarks           # addons, bookmarks, downloads, history, general
python run.py --case ADD-001,BM-004
python run.py --sanity                             # quick pass
python run.py --all --reruns 1                     # re-run failures once to separate flakes
python run.py --all --screenshot-steps             # picture after every step
python run.py --list                               # cases and automation status
python run.py --feature downloads -- -x -k pause   # raw pytest args after --
python run.py --case BM-004 --raw                  # pytest's own output (tracebacks, logs) to debug
```

The output is one line per test, grouped by feature: `[PASS]` / `[FAIL]` / `[ERR ]` / `[SKIP]`,
case id, case title, time, progress (`12/73`). Under a failure: `step:` (the case step that
failed), `expected:`, `error:` (one line) and `evidence:` (its `failure.txt`, read it next).
The run ends with the summary (verdict, totals per feature, failures, report paths).

Native tests need an unlocked, visible Windows desktop (not a minimized RDP session).
`--no-native` skips them; say so in the report when you use it.

## Outputs: `artifacts/test-results/`

The folder holds the latest run only: it is emptied when the next run starts. Read (or copy
elsewhere) the evidence of a failure before re-running it.

| path | content |
|------|---------|
| `report/index.html` | **the build's sanity report**: verdict, build info, one row per case (steps, expected, result, screenshot); the `report/` folder can be zipped and shared |
| `report/report.md` | same report in Markdown |
| `confluence/` | the same report as a Confluence page: `manifest.json` (title), `page.storage.html`, `page.md`, `attachments/` (one screenshot per test) |
| `results.json` | every test: outcome, case ids, steps, failed step, error, screenshot, evidence paths |
| `failures/<test>/` | `failure.txt` (read first), `page.png` (failing element outlined in red), `screen.png` (browser windows incl. native dialogs), `dom.txt`, `page.html`, `uia.txt`, `alert.txt` |
| `results/<test>.png` | final screenshot of every passed test (used by the report) |
| `steps/<test>/` | per-step screenshots (`--screenshot-steps`) |
| `report.html` | raw pytest-html report |
| `logs/` | chromedriver logs (`profiles/` too with `--keep-profile`) |

Rebuild the report (e.g. after editing case docs): `python -m sbtest.tools.report [--open]`.
Refresh the case overview with the latest results: `python -m sbtest.tools.case_overview`.

## Triage: each failure into exactly one bucket

1. **Product regression** - behaviour differs from the case's Expected. Evidence: case id,
   failed step, screenshots. Do not touch the test.
2. **UI changed, test outdated** - same behaviour, different markup/labels after the merge.
   Fix the page object (`sbtest/pages/`) or `config/native_ui.yaml`
   (`.agents/skills/sbtest-author/references/debugging.md`), re-run the feature.
3. **Environment** - driver/browser mismatch, locked desktop, proxy, crash of the machine.
   Fix it as the `fix:` lines of `setup.bat` say, re-run.
4. **Flaky test** - passes on re-run with no product change: find the race (missing wait,
   stale list read, shared data) and fix it; never add sleeps.

## Report

`run.py` ends with a summary: verdict, totals per feature, every failure with its evidence
path. `python -m sbtest.tools.summary` prints it again (`--json` for the same data as
JSON). Quote it, never infer numbers.
**BUILD PASSED** = no failed or error case among those run (skipped = not run). Say which
features were run - a `--feature bookmarks` run passes only bookmarks.

To publish on Confluence follow steps 7-8 of the `sbtest` skill
(`.agents/skills/sbtest/SKILL.md`): confirm with the user, then create the page from
`artifacts/test-results/confluence/` with the managing-jira-confluence skill.
