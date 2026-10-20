# sbtest - automated sanity tests for Samsung Internet for Windows (Chromium fork)

- Windows only. First time on a machine: `setup.bat`, edit `config/local.yaml`,
  `python -m sbtest.tools.doctor` (and `--target chrome` after `python -m sbtest.tools.get_chrome`).
- Skills: `sbtest-intake` (test cases/links -> testcases/*.md), `sbtest-author` (cases -> tests),
  `sbtest-run` (run, triage, Confluence report). Confluence itself is handled by the Confluence skill.
- Targets: `samsung` (internet://, sbtest/pages/samsung, config/native_ui/samsung.yaml) and
  `chrome` (reference, chrome://, sbtest/pages/chromium, config/native_ui/chromium.yaml).
- Tests: product tests per feature in `tests/features/<feature>/`; interaction examples in
  `tests/reference/` (catalogue: tests/reference/README.md).
- Framework self-tests (no browser): `python -m pytest framework_tests -q`.
- Never put selectors, internet:// URLs, machine paths or native UI names in tests.
- Explore before writing selectors: `python -m sbtest.tools.dom <page> --interactive`,
  `python -m sbtest.tools.uia_dump`.
