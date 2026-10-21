# sbtest - automated sanity tests for Samsung Internet / Samsung Browser for Windows

- Layout: `config/` settings, `sbtest/` framework, `tests/features/` + `tests/framework/` tests,
  `cases/` case docs, `resources/` (data, extensions, profiles, site), `docs/SETUP.md`.
- Windows only. First time on a machine: `setup.bat`, set `browser.exe` in `config/local.yaml`,
  `python -m sbtest.tools.doctor` (step by step: `docs/SETUP.md`).
- Skills (Agent Skills format) in `.agents/skills/<name>/SKILL.md`: `sbtest-intake` (test
  cases/links -> cases/*.md), `sbtest-explore` (request -> explore the real UI -> case + test;
  action catalogue), `sbtest-author` (framework API, conventions), `sbtest-run` (run, triage,
  per-build report, Confluence). If your agent does not load skills itself, read the SKILL.md
  that matches the task first, then the reference files it points to. Confluence itself is
  handled by the Confluence skill.
- Edit skills only in `.agents/skills/`, then `python -m sbtest.tools.sync_skills` (copies
  them to `.claude/skills/` for Claude Code; a framework test fails while the copy is stale).
- Report of a run: `artifacts/runs/<ts>/report/index.html` (+ `confluence/`); case overview:
  `python -m sbtest.tools.case_overview` -> `cases/TESTCASES.md`.
- Scratch exploration tests go in `tests/_scratch/` (git-ignored), helper `sbtest.tools.explore`.
- Browser: attach mode; navigation uses chrome://, the address bar shows internet://
  (`config/default.yaml`). Page objects: `sbtest/pages/`; browser UI names: `config/native_ui.yaml`.
- Tests: one folder per feature in `tests/features/<feature>/`; cases in `cases/<feature>/`
  (sanity cases `sanity.md`, IDs x-1xx; browser-UI flows `toolbar.md`).
- Framework self-tests (no browser): `python -m pytest tests/framework -q`.
- Never put selectors, internet:// URLs, machine paths or native UI names in tests.
- Explore before writing selectors: `python -m sbtest.tools.dom <page> --interactive`,
  `python -m sbtest.tools.uia_dump`.
