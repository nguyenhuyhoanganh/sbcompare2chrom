# Bookmarks - bookmark manager (sample cases)

## BM-001 Add a bookmark from the bookmark manager
- Priority: High
- Type: web
- Precondition: Clean profile
- Steps:
  1. Open the bookmark manager
  2. Open the Organize menu and choose "Add new bookmark"
  3. Enter a name and a URL, click Save
- Expected:
  - The new bookmark is listed with the given name
- Automated: tests/bookmarks/test_bookmark_manager.py::test_add_bookmark

## BM-002 Add a folder
- Priority: High
- Type: web
- Precondition: Clean profile
- Steps:
  1. Open the bookmark manager
  2. Organize menu > "Add new folder", enter a name, Save
- Expected:
  - The folder is listed in the list and in the folder tree
- Automated: tests/bookmarks/test_bookmark_manager.py::test_add_folder

## BM-003 Edit a bookmark
- Priority: High
- Type: web
- Precondition: Bookmarks bar contains "Static page 1"
- Steps:
  1. Open the bookmark manager
  2. Open the item menu of "Static page 1" and choose Edit
  3. Change the name to a new value, Save
- Expected:
  - The list shows the new name, the old name is gone
- Automated: tests/bookmarks/test_bookmark_manager.py::test_edit_bookmark

## BM-004 Delete a bookmark and undo
- Priority: High
- Type: web
- Precondition: Bookmarks bar contains "Static page 2"
- Steps:
  1. Open the bookmark manager
  2. Delete "Static page 2" from its item menu
  3. Click Undo on the toast
- Expected:
  - After step 2 the item is gone and a toast says it was deleted
  - After step 3 the item is back
- Automated: tests/bookmarks/test_bookmark_manager.py::test_delete_and_undo

## BM-005 Search bookmarks
- Priority: Medium
- Type: web
- Precondition: Several bookmarks exist (Alpha, Beta, Gamma, Delta)
- Steps:
  1. Open the bookmark manager
  2. Type "ta" in the search box
- Expected:
  - Only "Beta" and "Delta" are listed
- Automated: tests/bookmarks/test_bookmark_manager.py::test_search

## BM-006 Open a sub folder
- Priority: Medium
- Type: web
- Precondition: Folder "Work" with "Form page" and "Dialogs page"
- Steps:
  1. Open the bookmark manager, select folder "Work" in the tree
- Expected:
  - The list shows exactly "Form page" and "Dialogs page"
- Automated: tests/bookmarks/test_bookmark_manager.py::test_open_folder

## BM-010 Bookmark the current page with Ctrl+D
- Priority: High
- Type: native
- Precondition: Clean profile, a page is open
- Steps:
  1. Open "Static page 1"
  2. Press Ctrl+D, the bookmark bubble appears, click Done
  3. Open the bookmark manager
- Expected:
  - The bubble is shown after step 2
  - "Static page 1" is listed in the bookmark manager
- Automated: tests/bookmarks/test_bookmark_native.py::test_ctrl_d_bookmarks_page
