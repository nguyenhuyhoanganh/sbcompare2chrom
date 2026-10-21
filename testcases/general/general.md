# General browsing (sample cases)


## GEN-001 Back and forward navigation
- Priority: High
- Type: web
- Steps:
  1. Open "Static page 1", follow the link to "Static page 2"
  2. Go back, then forward
- Expected:
  - Titles follow page 1 -> page 2 -> page 1 -> page 2
- Automated: tests/features/general/test_navigation.py::test_back_forward
