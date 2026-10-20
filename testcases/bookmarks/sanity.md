# Bookmarks - sanity pass after a Chromium merge (Samsung Browser for Windows)

Flows as the Samsung UI does them (verified on Samsung Browser 31.0.0.55 / Chromium 148).
Bookmark manager basics shared with Chrome are in bookmark_manager.md (BM-001..BM-010).

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

## BM-109 Add a bookmark into a sub folder
- Priority: High
- Type: web
- Precondition: Bookmark bar contains folder "Work"
- Steps:
  1. Open the bookmark manager, select folder "Work" in the tree
  2. Right ⋮ > Add bookmark, enter Name and Web address, Save
- Expected:
  - The bookmark is listed in "Work" with the given address
  - It is not listed in Bookmark bar
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_add_bookmark_into_folder

## BM-110 Sort by name
- Priority: Medium
- Type: web
- Precondition: Bookmark bar contains Alpha, Beta, Gamma, Delta and folder "Folder X" (in that order)
- Steps:
  1. Open the bookmark manager
  2. Right ⋮ > Sort by name
- Expected:
  - The order becomes Folder X, Alpha, Beta, Delta, Gamma (folders first, then A-Z)
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_sort_by_name

## BM-111 Delete a folder with its bookmarks and undo
- Priority: High
- Type: web
- Precondition: Folder "Work" contains "Form page" and "Dialogs page"
- Steps:
  1. Tick "Work", click Delete
  2. Click Undo on the snack bar
- Expected:
  - After step 1 "Work" is gone from the list and the tree
  - After step 2 "Work" is back with both bookmarks inside
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_delete_folder_and_undo

## BM-112 Open all bookmarks of a folder in new tabs
- Priority: Medium
- Type: web
- Precondition: Folder "Work" contains 2 bookmarks
- Steps:
  1. Right click "Work" > Open all (2) in new tab
- Expected:
  - Two new tabs open: "Form page" and "Dialogs page"
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_open_all_in_new_tabs

## BM-113 Export bookmarks to an HTML file
- Priority: Medium
- Type: native
- Precondition: Bookmark bar contains Static page 1, Static page 2, Work
- Steps:
  1. Left ⋮ > Export bookmarks
  2. In the Windows Save As dialog (default name "bookmarks_<date>", HTML) save to a test folder
- Expected:
  - The HTML file is written and contains the bookmark titles and addresses
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_export_bookmarks

## BM-114 "Import bookmarks" opens the import settings
- Priority: Low
- Type: web
- Steps:
  1. Left ⋮ > Import bookmarks
- Expected:
  - Settings opens in a new tab on the import page
- Automated: tests/features/bookmarks/test_bookmarks_sanity.py::test_import_opens_settings
