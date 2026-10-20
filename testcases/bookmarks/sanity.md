# Bookmarks - sanity pass after a Chromium merge (Samsung Browser for Windows)

Flows as the Samsung UI does them (verified on Samsung Browser 31.0.0.55 / Chromium 148).
Bookmark manager basics shared with Chrome are in bookmark_manager.md (BM-001..BM-010).

## BM-101 Bookmark the current page with Ctrl+D
- Priority: High
- Type: native
- Precondition: Clean profile; local page "Static page 1"
- Steps:
  1. Open "Static page 1"
  2. Press Ctrl+D
  3. Open the bookmark manager
- Expected:
  - A "Page bookmarked." toast with an "Edit" button is shown
  - The star in the address bar turns into "Remove from Bookmarks"
  - "Static page 1" is listed in Bookmark bar
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_ctrl_d_bookmarks_current_page

## BM-102 Remove a bookmark with the star
- Priority: Medium
- Type: native
- Precondition: "Static page 1" is bookmarked (Ctrl+D)
- Steps:
  1. On "Static page 1" click the filled star in the address bar
  2. Open the bookmark manager
- Expected:
  - The star is no longer shown as bookmarked
  - "Static page 1" is not listed
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_star_removes_bookmark

## BM-103 Edit name and web address
- Priority: High
- Type: web
- Precondition: Bookmark bar contains "Static page 1"
- Steps:
  1. Open the bookmark manager
  2. Tick "Static page 1", click Edit in the toolbar
  3. Change Name and Web address, click Save
- Expected:
  - The list shows the new name with the new address; the old name is gone
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_edit_name_and_url

## BM-104 Edit from the right-click menu
- Priority: Medium
- Type: web
- Precondition: Bookmark bar contains "Static page 2"
- Steps:
  1. Open the bookmark manager
  2. Right click "Static page 2" > Edit, change the name, Save
- Expected:
  - The right-click menu offers Edit, Delete, Open all (1) in new tab / new window / Secret mode
  - The list shows the new name
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_edit_from_context_menu

## BM-105 Delete from the right-click menu and undo
- Priority: High
- Type: web
- Precondition: Bookmark bar contains "Static page 2"
- Steps:
  1. Open the bookmark manager
  2. Right click "Static page 2" > Delete
  3. Click Undo on the snack bar
- Expected:
  - After step 2 the item is gone and a snack bar says "1 bookmark deleted"
  - After step 3 the item is back
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_delete_from_context_menu_and_undo

## BM-106 Select all and delete
- Priority: Medium
- Type: web
- Precondition: Bookmark bar contains Static page 1, Static page 2 and folder Work
- Steps:
  1. Open the bookmark manager
  2. Click "Select all" in the toolbar, then "Delete all"
- Expected:
  - The header shows "3 selected"; the toolbar offers "Delete all" and "Deselect all"
  - The list is empty afterwards ("No bookmarks") and the snack bar reports the deletion
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_select_all_and_delete

## BM-107 Open a bookmark from the manager
- Priority: High
- Type: web
- Precondition: Bookmark bar contains "Static page 1"
- Steps:
  1. Open the bookmark manager
  2. Click "Static page 1"
- Expected:
  - "Static page 1" opens in a new tab
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_open_bookmark

## BM-108 Bookmarks are kept after restarting the browser
- Priority: High
- Type: web
- Precondition: Clean profile
- Steps:
  1. Create a folder in Bookmark bar and rename a seeded bookmark
  2. Close and reopen the browser on the same profile
  3. Open the bookmark manager
- Expected:
  - The folder and the renamed bookmark are still listed
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_bookmarks_survive_restart
