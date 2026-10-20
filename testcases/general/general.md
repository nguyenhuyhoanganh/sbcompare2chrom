# General browsing (sample cases)

Generic interactions (forms, uploads, dialogs, drag & drop, file dialogs, prompts ...) are
demonstrated by the reference suite in tests/reference/ - they need no case documents.

## GEN-001 Back and forward navigation
- Priority: High
- Type: web
- Steps:
  1. Open "Static page 1", follow the link to "Static page 2"
  2. Go back, then forward
- Expected:
  - Titles follow page 1 -> page 2 -> page 1 -> page 2
- Automated: tests/features/general/test_navigation.py::test_back_forward

## GEN-002 Link with target=_blank opens a new tab
- Priority: Medium
- Type: web
- Steps:
  1. On the popups page click "Open page 2 in new tab"
- Expected:
  - A new tab shows "Static page 2"; closing it returns to the first tab
- Automated: tests/features/general/test_navigation.py::test_link_opens_new_tab

## GEN-010 Type a URL in the address bar
- Priority: High
- Type: native
- Steps:
  1. Focus the address bar, type a local URL, press Enter
- Expected:
  - The page loads and the address bar shows its URL
- Automated: tests/features/general/test_navigation.py::test_omnibox_navigation
