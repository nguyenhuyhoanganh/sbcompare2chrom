# sbtest - automated sanity tests for Samsung Internet / Samsung Browser for Windows

- Layout: `config/` settings, `sbtest/` framework, `tests/features/` + `tests/framework/` tests,
  `cases/` case docs, `resources/` (data, extensions, profiles, site); setup and run: `README.md`.
- Windows only. Two steps: `setup.bat --exe "<SamsungInternet.exe>"` (installs packages, checks
  the machine with doctor, gets chromedriver; must end with READY), then `python run.py ...`
  with the same `--exe`. Re-check only: `python -m sbtest.tools.doctor`.
- Skills (Agent Skills format) in `.agents/skills/<name>/SKILL.md`: `sbtest-intake` (test
  cases/links -> cases/*.md), `sbtest-explore` (request -> explore the real UI -> case + test;
  action catalogue), `sbtest-author` (framework API, conventions), `sbtest-run` (run, triage,
  per-build report, Confluence), `sbtest` (step by step: ask scope, exe and
  Confluence target -> setup.bat (check) -> run -> triage -> publish with `managing-jira-confluence`;
  `/sbtest` where the agent offers skills as commands). If your agent does not load skills
  itself, read the SKILL.md that matches the task first, then the reference files it points
  to. Confluence itself is handled by the Confluence skill `managing-jira-confluence`.
- `.agents/skills/` is the only copy of the skills: edit them there; `tests/framework` checks
  their frontmatter and links.
- Results of the latest run (emptied when a run starts): `artifacts/test-results/`, report
  `report/index.html` (+ `confluence/`, `failures/`, `logs/`); case overview:
  `python -m sbtest.tools.case_overview` -> `cases/TESTCASES.md`.
- Scratch exploration tests go in `tests/_scratch/` (git-ignored), helper `sbtest.tools.explore`;
  their failures/logs go to `artifacts/explore/scratch-run/` (never into `test-results/`).
- Browser: attach mode; navigation uses chrome://, the address bar shows internet://
  (`config/default.yaml`). Page objects: `sbtest/pages/`; browser UI names: `config/native_ui.yaml`.
- Tests: one folder per feature in `tests/features/<feature>/`; cases in `cases/<feature>/`
  (sanity cases `sanity.md`, IDs x-1xx; browser-UI flows `toolbar.md`).
- Framework self-tests (no browser): `python -m pytest tests/framework -q`.
- Never put selectors, internet:// URLs, machine paths or native UI names in tests.
- Explore before writing selectors: `python -m sbtest.tools.dom <page> --interactive`,
  `python -m sbtest.tools.uia_dump`.
