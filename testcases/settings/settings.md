# Settings (sample cases)

## SET-001 Toggle "Ask where to save each file"
- Priority: High
- Type: web
- Steps:
  1. Open Settings > Downloads
  2. Turn on "Ask where to save each file before downloading"
- Expected:
  - The toggle is on and the preference download.prompt_for_download is true
- Automated: tests/features/settings/test_settings.py::test_toggle_ask_where_to_save

## SET-002 Search settings
- Priority: Medium
- Type: web
- Steps:
  1. Open Settings, search "downloads"
- Expected:
  - The Downloads section is shown in the results
- Automated: tests/features/settings/test_settings.py::test_search_settings

## SET-003 Setting persists after restart
- Priority: High
- Type: web
- Steps:
  1. Turn on "Ask where to save each file before downloading"
  2. Restart the browser, open Settings > Downloads
- Expected:
  - The toggle is still on
- Automated: tests/features/settings/test_settings.py::test_setting_persists_after_restart

## SET-004 On startup: open a specific page
- Priority: Medium
- Type: web
- Steps:
  1. Settings > On startup: choose "Open a specific page or set of pages"
- Expected:
  - The radio is selected and session.restore_on_startup == 4
- Automated: tests/features/settings/test_settings.py::test_on_startup_specific_pages
