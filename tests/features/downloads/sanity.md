# Downloads - sanity pass after a Chromium merge (Samsung Browser for Windows)

Flows as the Samsung UI does them (verified on Samsung Browser 31.0.0.55 / Chromium 148).
Basics are in downloads.md (DL-0xx).

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
  1. Download sample.txt, data.bin and photo.png (image/png)
  2. Open Downloads, choose Document, Others, Image, Video in the side bar
- Expected:
  - Document lists sample.txt only, Others data.bin only, Image photo.png only, Video nothing
- Automated: tests/features/downloads/test_downloads_sanity.py::test_category_filter

## DL-103 Search downloads
- Priority: Medium
- Type: web
- Steps:
  1. Download sample.txt and data.bin
  2. Type "ta.bin" (part of the name) in the search box
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

## DL-107 Remove an entry and undo
- Priority: Medium
- Type: web
- Steps:
  1. Download photo.png, open Downloads
  2. Click X on the row, then Undo on the snack bar
- Expected:
  - After X the row is gone; after Undo it is back
- Automated: tests/features/downloads/test_downloads_sanity.py::test_remove_and_undo

## DL-108 Same file downloaded twice gets a new name
- Priority: High
- Type: web
- Steps:
  1. Download sample.txt twice
- Expected:
  - The folder has sample.txt and "sample (1).txt"; both are listed
- Automated: tests/features/downloads/test_downloads_sanity.py::test_duplicate_name

## DL-109 "Copy link" copies the download address
- Priority: Low
- Type: native
- Steps:
  1. Download sample.txt, open Downloads
  2. Click the "Copy link" icon of the row
- Expected:
  - The Windows clipboard holds the address the file was downloaded from
- Automated: tests/features/downloads/test_downloads_sanity.py::test_copy_link

## DL-110 Toolbar Downloads bubble lists the finished file
- Priority: Medium
- Type: native
- Steps:
  1. Download sample.txt from a page
- Expected:
  - The toolbar Downloads bubble opens with "sample.txt 2,048 B • Done"
- Automated: tests/features/downloads/test_downloads_sanity.py::test_toolbar_bubble

## DL-111 Link with a download attribute saves under that name
- Priority: Medium
- Type: web
- Steps:
  1. Click a link to page1.html that has download="saved-page1.html"
- Expected:
  - saved-page1.html is in the download folder and listed in Downloads
- Automated: tests/features/downloads/test_downloads_sanity.py::test_download_attribute
