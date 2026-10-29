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

## GEN-002 Open a link in a new tab from the right-click menu
- Priority: High
- Type: native
- Precondition: a web page with a link ("Static page 1", link "Next" to "Static page 2")
- Steps:
  1. Open "Static page 1"
  2. Right-click the link "Next" and choose "Open link in new tab"
- Expected:
  - A new tab opens with "Static page 2"
  - The first tab still shows "Static page 1"
- Automated: tests/features/general/test_navigation.py::test_open_link_in_new_tab
