---
name: sbtest-run
description: Runs the Samsung Internet automated tests (all, by feature, or by test case id) against a build, triages the failures and publishes the run report to Confluence. Use when asked to run/execute the tests, check a new build after a Chromium merge, re-run failures, explain failures, or share results.
---

# Run, triage, report

Copy this checklist into your reply and tick it off:

```
- [ ] doctor green (first run on the machine / new build)
- [ ] tests run (selection noted)
- [ ] every failure in one triage bucket, buckets 2-4 fixed and re-run
- [ ] report published (if asked) and verdict + triage table + link sent
```

## First time on a machine

`setup.bat`, set `browser.exe` in `config/local.yaml`, then `python -m sbtest.tools.doctor`
and fix every FAIL (step by step: `docs/SETUP.md`).

## Run

```
python run.py --all                                # every feature (tests/features)
python run.py --feature addons,bookmarks
python run.py --case ADD-001,BM-004
python run.py --sanity                             # quick pass
python run.py --all --reruns 1                     # re-run failures once to separate flakes
python run.py --all --screenshot-steps             # picture after every step
python run.py --list                               # cases and automation status
python run.py --feature downloads -- -x -k pause   # raw pytest args after --
```

Native tests need an unlocked, visible Windows desktop (not a minimized RDP session).
`--no-native` skips them; say so in the report when you use it.

Run one feature only: `--feature addons` (or `bookmarks`, `downloads`, `history` ...);
each feature's tests are in `tests/features/<feature>/` and its cases in `cases/<feature>/`.

## Outputs: `artifacts/test-results/`

The folder holds the latest run only: it is emptied when the next run starts. Read (or copy
elsewhere) the evidence of a failure before re-running it.

| path | content |
|------|---------|
| `report/index.html` | **the build's sanity report**: verdict BUILD PASSED / FAILED, build info (Samsung version, Chromium, machine, date, selection), one row per case: ID, name + precondition, steps, expected, result (failed step + error + executed steps on failure), screenshot of how it ended. The `report/` folder (with `img/`) can be zipped and shared |
| `report/report.md` | same report in Markdown |
| `confluence/` | the same report as a Confluence page: `manifest.json` (title), `page.storage.html`, `page.md`, `attachments/` (one screenshot per test) |
| `results.json` | every test: outcome, case ids, steps, failed step, error, screenshot, evidence paths |
| `failures/<test>/` | `failure.txt` (read first), `page.png` (failing element outlined in red), `screen.png` (whole screen, native dialogs), `dom.txt`, `page.html`, `uia.txt`, `alert.txt` |
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
   Fix the setup (`doctor`), re-run.
4. **Flaky test** - passes on re-run with no product change: find the race (missing wait,
   stale list read, shared data) and fix it; never add sleeps.

## Report

`python -m sbtest.tools.summary` prints the verdict, totals per feature and every failure
with its evidence path (`--json` for the same data as JSON). For the guided end-to-end flow
(questions, doctor, run, publish) use the `sbtest-sanity-workflow` skill.

The verdict for a build is the header of `report/index.html`: **BUILD PASSED** = no failed or
error case among those run (skipped = not run, e.g. native tests without a desktop). Say which
features were run (`Selection` row) - a `--feature bookmarks` run passes only bookmarks.

To publish, use the **managing-jira-confluence** skill to create a new page from `artifacts/test-results/confluence/`:
title from `manifest.json`, body `page.storage.html` (Confluence storage format; use `page.md`
if the skill takes Markdown), and upload every file in `attachments/` to that page (the body
already references them by file name). Put it where the user asked (space / parent page).
If failures were triaged, add a short "Triage" section to the page: case id | bucket | reason.
Then reply with the verdict, totals per feature, the triage table and the page link.
