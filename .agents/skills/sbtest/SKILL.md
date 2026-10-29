---
name: sbtest
description: Guides a full sanity check of a Samsung Internet / Samsung Browser for Windows build step by step - asks which part to test (all, sanity pass, features, case IDs), asks for the SamsungInternet.exe path and the Confluence destination, checks the machine, runs the sbtest suite, triages failures and publishes the report as a Confluence page with the managing-jira-confluence skill. Use when the user wants to test a build end to end, check a new build after a Chromium merge, or "run the tests and put the result on Confluence".
---

# Sanity workflow: questions -> run -> report -> Confluence

Ask in the user's language. Use your agent's question tool when it has one (with the options
below), else ask in plain text, and **wait for each answer** - never guess a path,
a selection or a Confluence location. Commands run in the repo root on the Windows machine;
`python` means `.venv\Scripts\python.exe` (created by `setup.bat` in step 4).

How to call the two commands from your shell (repo root; agent shells often do not run
programs from the current folder, so always keep the `.\` / `./`):

| shell | prepare the machine | run tests |
|---|---|---|
| PowerShell | `.\setup.bat --exe "<path>"` | `.\.venv\Scripts\python.exe run.py ...` |
| cmd | `.\setup.bat --exe "<path>"` | `.venv\Scripts\python run.py ...` |
| Git Bash | `./setup.bat --exe "<path>"` | `.venv/Scripts/python.exe run.py ...` |

`setup.bat` never waits for input when nobody can answer: without `--exe` it uses
`browser.exe` of `config/local.yaml` or the installed Samsung Browser.

Copy this checklist into your reply and tick it off:

```
- [ ] 1 scope chosen          - [ ] 2 exe path confirmed   - [ ] 3 Confluence target known
- [ ] 4 setup READY          - [ ] 5 tests run            - [ ] 6 result read + triaged
- [ ] 7 publish confirmed     - [ ] 8 page created + attachments uploaded
- [ ] 9 final answer sent (verdict, totals, triage, link)
```

## 1. Ask what to test

Options (several features may be combined; `--sanity` can be added to a feature selection):

| answer | arguments |
|---|---|
| everything | `--all` |
| quick sanity pass | `--sanity` |
| some features: add-ons, bookmarks, downloads, history, general | `--feature addons,bookmarks` |
| some test cases | `--case BM-113,DL-003` |

Not sure which cases exist? `python run.py --list` prints them per feature. Also ask whether
the desktop stays free during the run: native tests drive the real mouse and keyboard; if the
user needs the machine, add `--no-native` (and say so in the report).

Then ask how each test should be shown - a video, or pictures - and where:

| answer | arguments |
|---|---|
| nothing extra | (nothing) |
| video of each test, on Confluence for failed cases (recommended) | `--record` |
| pictures of every click / typing, on Confluence for failed cases | `--screenshot-steps` |
| ... on Confluence for every case | add `--confluence-steps all` |
| ... only in the local report | add `--confluence-steps none` |

The video shows the browser windows, the running case step as a caption and each click /
typing framed in red; the pictures are one per interaction plus one per step. Either makes
the run ~10% longer.

## 2. Ask for the exe

Show the current value first (`browser.exe` in `config/local.yaml`, if any) and ask the user
to confirm it or give the full path of `SamsungInternet.exe` of the build to test. Use it as
`--exe "<path>"` on every command below (do not edit `config/local.yaml` unless asked).

## 3. Ask where to publish

Confluence space and parent page (or a page link to put it under), or "do not publish".
Asking now lets the run finish without waiting for the user.

## 4. Prepare and check the machine

```
.\setup.bat --exe "<path>"
```

It installs the packages, then checks the machine (keyboard, Chromium version, chromedriver -
downloaded when missing -, browser start, internal pages, toolbar) and ends with READY or
NOT READY. Every `[FAIL]` line has a `fix:` line: apply it (more: `README.md`) and run
`setup.bat` again; never start the tests on NOT READY. Report the WARN lines and what you fixed.

## 5. Run

```
python run.py <arguments from step 1> --exe "<path>"
```

`--all` takes about 8-10 minutes (more on a slow machine), a feature 1-3 minutes: start long
runs in the background or with a timeout of at least 20 minutes - a default 2-minute tool
timeout kills the run halfway. The run first empties `artifacts/test-results/` - copy that
folder elsewhere beforehand if the previous result must be kept.

## 6. Read the result and triage

`run.py` ended with a summary; print it again any time with:

```
python -m sbtest.tools.summary
```

It shows the verdict (BUILD PASSED / FAILED), totals per feature, each failure with its
failed step, error and `failure.txt`. Quote these numbers; never infer them.
For each failure read `failure.txt`, `page.png`, `screen.png` and put it in exactly one bucket
of the `sbtest-run` skill (`.agents/skills/sbtest-run/SKILL.md`, section "Triage"):
product regression / UI changed, test outdated / environment / flaky test.

Ask the user before changing any test, page object or ui map. If you fix something, re-run
the **same arguments as step 5** (not only the failed cases): the run replaces the whole
result folder, and the report must cover the full selection.

## 7. Confirm before publishing

Show the user: page title (`confluence_title` from the summary), destination, verdict and
the triage table. Publish only after a yes. "Do not publish" in step 3 -> skip to step 9.

## 8. Publish with the managing-jira-confluence skill

Use the **managing-jira-confluence** skill to create a NEW page under the destination:

- title: `title` in `artifacts/test-results/confluence/manifest.json`
- body: `page.storage.html` (Confluence storage format); use `page.md` only if the skill
  takes Markdown
- upload every file listed in `attachments` of `manifest.json` (= every file of `attachments/`)
  to that page - the body references them by file name; with step pictures these include
  `<case>_NN-I_<kind>.jpg`, shown in one collapsed "Expand" block per case under each table.
  Many files: upload them in batches if the skill limits a call, and check the count
- failures triaged -> add a "Triage" section: case id | bucket | reason

The skill is not available -> stop and give the user the folder
`artifacts/test-results/confluence/` to upload by hand.

## 9. Final answer

Verdict, build (Samsung + Chromium version), selection, totals per feature, the triage table,
skipped tests and why (`--no-native`, no desktop), the Confluence page link, and the local
report `artifacts/test-results/report/index.html` ("Step pictures" under each case when they
were taken).
