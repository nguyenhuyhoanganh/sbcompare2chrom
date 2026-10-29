# History (sample cases)

## HIS-001 Visited pages are listed newest first
- Priority: High
- Type: web
- Steps:
  1. Visit page "Alpha", then "Beta"
  2. Open History
- Expected:
  - "Beta" is listed above "Alpha"
- Automated: tests/features/history/test_history.py::test_visited_pages_listed

## HIS-002 Search history
- Priority: Medium
- Type: web
- Steps:
  1. Visit "Alpha", "Beta", "Gamma"; open History
  2. Search "Gam"
- Expected:
  - Only "Gamma" is listed
- Automated: tests/features/history/test_history.py::test_search_history

## HIS-003 Delete selected entries
- Priority: High
- Type: web
- Steps:
  1. Visit "Alpha", "Beta"; open History
  2. Select "Alpha", click Delete, confirm Remove
- Expected:
  - "Alpha" is gone, "Beta" stays
- Automated: tests/features/history/test_history.py::test_delete_selected

## HIS-004 Remove one entry from its menu
- Priority: Medium
- Type: web
- Steps:
  1. Visit "Alpha"; open History
  2. Item menu > "Remove from history"
- Expected:
  - History is empty
- Automated: tests/features/history/test_history.py::test_remove_from_menu

## HIS-005 Open a page from history
- Priority: Medium
- Type: web
- Steps:
  1. Visit "Alpha"; open History; click "Alpha"
- Expected:
  - The page "Alpha" is loaded
- Automated: tests/features/history/test_history.py::test_open_from_history

## HIS-006 Open History with Ctrl+H
- Priority: Medium
- Type: native
- Steps:
  1. Press Ctrl+H
- Expected:
  - A tab with the History page is opened
- Automated: tests/features/history/test_history.py::test_ctrl_h_opens_history
