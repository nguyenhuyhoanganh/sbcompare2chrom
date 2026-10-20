---
name: sbtest-run
description: Run the Samsung Internet automated sanity suite (all, by feature, or by test case id) against a SamsungInternet.exe build and triage the results - e.g. after merging a new Chromium release. Use when asked to run/execute the tests, check a new build, re-run failures, or explain why tests failed.
---

# Running and triaging the sanity suite

## Run

```
python run.py --exe "<path>\SamsungInternet.exe" --all
python run.py --exe ... --feature bookmarks,history
python run.py --exe ... --case BM-001,DL-004
python run.py --exe ... --sanity                  # quick pass (@sanity tests)
python run.py --exe ... --all --reruns 1          # re-run failures once to separate flakes
python run.py --list                              # cases per feature and what is automated
python run.py --exe ... --feature downloads -- -x -k pause    # raw pytest args after --
```

The exe can also come from `SB_EXE` or `config/local.yaml`. chromedriver is resolved
automatically (config -> `drivers/<major>/` -> download); offline machines need
`browser.chromedriver` or a driver in `drivers/<major>/chromedriver.exe`. Best: build the
`chromedriver` target from the same fork checkout as the browser.

Native tests need an interactive, unlocked Windows desktop; on headless / CI agents
without a desktop use `--no-native` and report that native cases were not run.

## Output

`artifacts/runs/<timestamp>/`: `report.html` (self-contained), `junit.xml`,
`failures/<test>/` (`page.png`, `dom.txt`, `page.html`, `screen.png`, `uia.txt`, `alert.txt`).
Console has, per failure, the `sbtest steps` section showing the failed doc step.

## Triage each failure into exactly one bucket

1. **Product regression** - behaviour differs from the case's Expected (wrong data, missing
   item, crash). Evidence: screenshot + step + case ID. Do not touch the test.
2. **UI changed, test outdated** - element renamed/moved after the merge, expected behaviour
   unchanged. Fix selectors in the page object / `native_ui.yaml` (see
   `.claude/skills/sbtest-author/references/debugging.md`), re-run the feature.
3. **Environment** - driver/browser version mismatch, no desktop for native tests, machine
   crash, network. Fix the setup, re-run.
4. **Flaky test** - passes on re-run with no product change. Find the race (missing wait,
   stale list read, shared data) and fix it; never add sleeps.

Report as a table: case ID | test | bucket | one-line reason | evidence path. Totals per
feature (passed / failed / skipped-native / not automated from `python run.py --list`).
