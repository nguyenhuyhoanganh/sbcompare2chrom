# Bookmarks - browser toolbar (Samsung Browser for Windows)

Bookmarking from the browser's own UI: Ctrl+D toast, star in the address bar, Bookmarks panel
(toolbar "Bookmarks" button). All native (Windows). Verified on Samsung Browser 31.0.0.55.

## BM-113 Bookmark the page with Ctrl+D and rename it from the toast
- Priority: High
- Type: native
- Precondition: Clean profile; local page "Static page 1"
- Steps:
  1. Open "Static page 1", click into the page (the star only shows when the address bar
     has no focus, build 155+)
  2. Press Ctrl+D
  3. Click "Edit" on the toast, change the name, Save
  4. Open the bookmark manager
- Expected:
  - Step 2: toast "Page bookmarked." with an "Edit" button; the star turns into "Remove from Bookmarks"
  - Step 3: the edit bubble shows "Bookmark name" and "Bookmark URL" (address shown without http://)
  - Step 4: the bookmark is listed with the new name only
- Automated: tests/features/bookmarks/test_bookmarks_toolbar.py::test_ctrl_d_toast_and_rename

## BM-114 Remove a bookmark with the star
- Priority: Medium
- Type: native
- Precondition: "Static page 1" is bookmarked (Ctrl+D after clicking into the page: the star
  only shows when the address bar has no focus, build 155+)
- Steps:
  1. On "Static page 1" click the filled star in the address bar
  2. Open the bookmark manager
- Expected:
  - The star is no longer shown as bookmarked
  - "Static page 1" is not listed
- Automated: tests/features/bookmarks/test_bookmarks_toolbar.py::test_star_removes_bookmark

## BM-115 Browse the Bookmarks panel and open a bookmark
- Priority: High
- Type: native
- Precondition: Bookmark bar contains Static page 1, Static page 2 and folder Work
- Steps:
  1. Click the toolbar "Bookmarks" button
  2. Open "Bookmark bar" in the panel
  3. Click "Static page 1"
- Expected:
  - The panel shows the tree "PC bookmarks" > "Bookmark bar" with Add bookmark, Create folder, Expand buttons
  - "Bookmark bar" lists Static page 1, Static page 2 and Work
  - "Static page 1" opens
- Automated: tests/features/bookmarks/test_bookmarks_toolbar.py::test_panel_browse_and_open

## BM-116 Add the current page from the panel, open the manager with Expand
- Priority: Medium
- Type: native
- Steps:
  1. Open a page, toolbar "Bookmarks" > "Add bookmark", click into the page (the star only
     shows when the address bar has no focus, build 155+)
  2. Open the panel again, click "Expand"
- Expected:
  - Step 1: the page is bookmarked (star filled)
  - Step 2: the bookmark manager opens in a tab and finds the page
- Automated: tests/features/bookmarks/test_bookmarks_toolbar.py::test_panel_add_page_and_expand
