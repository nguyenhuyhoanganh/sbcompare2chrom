# Downloads (sample cases)

## DL-001 Download a file
- Priority: High
- Type: web
- Steps:
  1. Open the downloads test page, click "sample.txt"
  2. Open the Downloads page
- Expected:
  - The file exists on disk with the right size
  - "sample.txt" is listed
- Automated: tests/features/downloads/test_downloads.py::test_download_file

## DL-002 Remove an entry from the list
- Priority: High
- Type: web
- Steps:
  1. Download "sample.txt"; open Downloads
  2. Click "Delete from history" on the entry
- Expected:
  - The entry is gone from the list; the file stays on disk
- Automated: tests/features/downloads/test_downloads.py::test_remove_entry_keeps_file

## DL-003 Clear all
- Priority: Medium
- Type: web
- Steps:
  1. Download two files; open Downloads; click "Clear all"
- Expected:
  - The list is empty
- Automated: tests/features/downloads/test_downloads.py::test_clear_all

## DL-004 Pause and resume
- Priority: Medium
- Type: web
- Steps:
  1. Start the slow 10 MB download; open Downloads
  2. Pause it, then Resume
- Expected:
  - Status shows "Paused" after pause, the download completes after resume
- Automated: tests/features/downloads/test_downloads.py::test_pause_resume

## DL-010 Ask where to save -> Save As dialog
- Priority: Medium
- Type: native
- Precondition: Setting "Ask where to save each file" is on
- Steps:
  1. Click "sample.txt" on the downloads page
  2. In the Save As dialog enter a new file name, Save
- Expected:
  - The file is saved with the chosen name
- Automated: tests/features/downloads/test_downloads.py::test_save_as_dialog
