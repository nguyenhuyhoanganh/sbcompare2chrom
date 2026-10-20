# History - sanity pass after a Chromium merge (Samsung Browser for Windows)

Flows as the Samsung UI does them (verified on Samsung Browser 31.0.0.55 / Chromium 148).
Basics shared with Chrome are in history.md (HIS-001..HIS-010).

## HIS-101 Entries show title, domain and time under a day header
- Priority: High
- Type: web
- Precondition: Clean profile
- Steps:
  1. Visit Alpha, then Beta (local pages)
  2. Open History
- Expected:
  - Beta is above Alpha
  - Each entry shows its domain (127.0.0.1) and a visit time
  - The entries are grouped under "Today - <date>"
- Automated: tests/features/history/test_history_sanity.py::test_entry_details

## HIS-102 Clear history
- Priority: High
- Type: web
- Precondition: Some pages visited
- Steps:
  1. Open History
  2. Click "Clear history" in the toolbar and confirm
- Expected:
  - The list is empty
- Automated: tests/features/history/test_history_sanity.py::test_clear_history

## HIS-103 Time filter
- Priority: Medium
- Type: web
- Precondition: Pages visited just now
- Steps:
  1. Open History
  2. Tick only "Last hour"; then only "Yesterday"; then "Yesterday" + "Today"; then "All time"
- Expected:
  - The time filters are check boxes; several ranges can be ticked and add up
  - Last hour, Yesterday + Today and All time list the pages; Yesterday alone does not
- Automated: tests/features/history/test_history_sanity.py::test_time_filter

## HIS-104 Delete a whole day
- Priority: Medium
- Type: web
- Precondition: Alpha and Beta visited today
- Steps:
  1. Open History
  2. Tick the "Today - <date>" check box, click Delete
- Expected:
  - Both entries are gone
- Automated: tests/features/history/test_history_sanity.py::test_delete_whole_day

## HIS-105 History is kept after restarting the browser
- Priority: High
- Type: web
- Steps:
  1. Visit Alpha
  2. Close and reopen the browser on the same profile
  3. Open History
- Expected:
  - Alpha is listed
- Automated: tests/features/history/test_history_sanity.py::test_history_survives_restart

## HIS-106 "Clear browsing data" link
- Priority: Low
- Type: web
- Steps:
  1. Open History, click "Clear browsing data" in the side bar
- Expected:
  - Settings > Clear browsing data opens
- Automated: tests/features/history/test_history_sanity.py::test_clear_browsing_data_link
