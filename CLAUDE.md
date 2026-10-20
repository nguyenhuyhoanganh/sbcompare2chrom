# sbtest - automated sanity tests for Samsung Internet for Windows (Chromium fork)

- Writing/fixing tests from test cases: use the `sbtest-author` skill (`.claude/skills/sbtest-author/SKILL.md`).
- Running a build and triaging results: use the `sbtest-run` skill.
- Python 3.10+, `pip install -r requirements.txt`. Tests: `python run.py ...` (wraps pytest).
- Framework self-tests (no browser): `python -m pytest framework_tests -q`.
- Never hardcode `chrome://` URLs, machine paths or native UI names in tests: they live in
  `config/` (`pages`, `local.yaml`, `native_ui.yaml`).
- Explore before writing selectors: `python -m sbtest.tools.dom <page> --interactive`,
  `python -m sbtest.tools.uia_dump`.
