# Downloads - sanity pass after a Chromium merge (Samsung Browser for Windows)

Flows as the Samsung UI does them (verified on Samsung Browser 31.0.0.55 / Chromium 148).
Basics shared with Chrome are in downloads.md (DL-001..DL-010).

## DL-101 Finished download shows name, size and source
- Priority: High
- Type: web
- Steps:
  1. Download sample.txt (2 KB) from the local downloads page
  2. Open Downloads
- Expected:
  - sample.txt is listed under "Today" with its size (2.05 KB) and source link 127.0.0.1
  - The file is in the download folder
- Automated: tests/features/downloads/test_downloads_sanity.py::test_entry_details

## DL-102 Category filter
- Priority: Medium
- Type: web
- Steps:
  1. Download sample.txt and data.bin
  2. Open Downloads, choose Document, Others, Image in the side bar
- Expected:
  - Document lists sample.txt only, Others lists data.bin only, Image lists nothing
- Automated: tests/features/downloads/test_downloads_sanity.py::test_category_filter

## DL-103 Search downloads
- Priority: Medium
- Type: web
- Steps:
  1. Download sample.txt and data.bin
  2. Type "data" in the search box
- Expected:
  - Only data.bin is listed
- Automated: tests/features/downloads/test_downloads_sanity.py::test_search

## DL-104 Cancel a download in progress
- Priority: High
- Type: web
- Steps:
  1. Start the slow 10 MB download
  2. Open Downloads, click Cancel on the row
- Expected:
  - The row is removed and a snack bar says "slow.bin removed from Downloads." (with Undo)
  - The toolbar Downloads bubble shows slow.bin as "Canceled"
  - No slow.bin is left in the download folder
- Automated: tests/features/downloads/test_downloads_sanity.py::test_cancel_in_progress

## DL-105 Open Downloads with Ctrl+J
- Priority: Medium
- Type: native
- Steps:
  1. Press Ctrl+J
- Expected:
  - The Downloads page opens
- Automated: tests/features/downloads/test_downloads_sanity.py::test_ctrl_j_opens_downloads

## DL-106 "Show in folder" opens File Explorer on the file
- Priority: Medium
- Type: native
- Steps:
  1. Download sample.txt, open Downloads
  2. Click the "Show in folder" icon of the row
- Expected:
  - File Explorer opens the download folder with sample.txt selected
- Automated: tests/features/downloads/test_downloads_sanity.py::test_show_in_folder
