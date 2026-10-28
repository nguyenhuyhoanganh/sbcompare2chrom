---
name: sbtest
description: Guides a full sanity check of a Samsung Internet / Samsung Browser for Windows build step by step - asks which part to test (all, sanity pass, features, case IDs), asks for the SamsungInternet.exe path and the Confluence destination, checks the machine, runs the sbtest suite, triages failures and publishes the report as a Confluence page with the managing-jira-confluence skill. Use when the user wants to test a build end to end, check a new build after a Chromium merge, or "run the tests and put the result on Confluence".
---

# Sanity workflow: questions -> run -> report -> Confluence

Ask in the user's language. Use your question tool (Cline: `ask_followup_question` with
options; Claude Code: `AskUserQuestion`) and **wait for each answer** - never guess a path,
a selection or a Confluence location. Commands run in the repo root on the Windows machine;
`python` means `.venv\Scripts\python.exe` (missing `.venv` -> run `setup.bat` first).

Copy this checklist into your reply and tick it off:

```
- [ ] 1 scope chosen          - [ ] 2 exe path confirmed   - [ ] 3 Confluence target known
- [ ] 4 doctor green          - [ ] 5 tests run            - [ ] 6 result read + triaged
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

## 2. Ask for the exe

Show the current value first (`browser.exe` in `config/local.yaml`, if any) and ask the user
to confirm it or give the full path of `SamsungInternet.exe` of the build to test. Use it as
`--exe "<path>"` on every command below (do not edit `config/local.yaml` unless asked).

## 3. Ask where to publish

Confluence space and parent page (or a page link to put it under), or "do not publish".
Asking now lets the run finish without waiting for the user.

## 4. Check the machine

```
python -m sbtest.tools.doctor --exe "<path>"
```

Every line must be OK. A FAIL -> fix it as `docs/SETUP.md` says (driver, proxy, desktop) and
run doctor again; do not start the tests on a red doctor. Report what you fixed.

## 5. Run

```
python run.py <arguments from step 1> --exe "<path>"
```

`--all` takes about 8-10 minutes. The run first empties `artifacts/test-results/` - copy that
folder elsewhere beforehand if the previous result must be kept.

## 6. Read the result and triage

```
python -m sbtest.tools.summary
```

It prints the verdict (BUILD PASSED / FAILED), totals per feature, each failure with its
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
- upload every file of `attachments/` to that page - the body references them by file name
- failures triaged -> add a "Triage" section: case id | bucket | reason

The skill is not available -> stop and give the user the folder
`artifacts/test-results/confluence/` to upload by hand.

## 9. Final answer

Verdict, build (Samsung + Chromium version), selection, totals per feature, the triage table,
skipped tests and why (`--no-native`, no desktop), the Confluence page link, and the local
report `artifacts/test-results/report/index.html`.
