# sbtest - automated sanity tests for Samsung Internet / Samsung Browser for Windows

- Windows only. First time on a machine: `setup.bat`, set `browser.exe` in `config/local.yaml`,
  `python -m sbtest.tools.doctor` (step by step: `SETUP.md`).
- Skills: `sbtest-intake` (test cases/links -> testcases/*.md), `sbtest-explore` (request ->
  explore the real UI -> case + test; action catalogue), `sbtest-author` (framework API,
  conventions), `sbtest-run` (run, triage, per-build report, Confluence). Confluence itself is
  handled by the Confluence skill.
- Report of a run: `artifacts/runs/<ts>/report/index.html` (+ `confluence/`); case overview:
  `python -m sbtest.tools.case_overview` -> `testcases/TESTCASES.md`.
- Scratch exploration tests go in `tests/_scratch/` (git-ignored), helper `sbtest.tools.explore`.
- Browser: attach mode; navigation uses chrome://, the address bar shows internet://
  (`config/default.yaml`). Page objects: `sbtest/pages/`; browser UI names: `config/native_ui.yaml`.
- Tests: one folder per feature in `tests/features/<feature>/`; cases in `testcases/<feature>/`
  (sanity cases `sanity.md`, IDs x-1xx; browser-UI flows `toolbar.md`).
- Framework self-tests (no browser): `python -m pytest framework_tests -q`.
- Never put selectors, internet:// URLs, machine paths or native UI names in tests.
- Explore before writing selectors: `python -m sbtest.tools.dom <page> --interactive`,
  `python -m sbtest.tools.uia_dump`.
