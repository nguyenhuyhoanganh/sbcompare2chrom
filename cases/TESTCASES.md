# Danh sách test case - sbtest

File sinh tự động bởi `python -m sbtest.tools.case_overview` từ `cases/**/*.md` và marker của test.
Đừng sửa tay: sửa file case gốc rồi chạy lại lệnh. Nội dung case giữ nguyên tiếng Anh như file gốc.

**73 test case**, tất cả đã có script tự động (54 web, 19 native).

| Feature | Prefix | Số case | Web | Native | Sanity |
|---|---|---:|---:|---:|---:|
| Add-ons | ADD | 19 | 11 | 8 | 7 |
| Bookmarks | BM | 22 | 17 | 5 | 9 |
| Downloads | DL | 16 | 11 | 5 | 4 |
| History | HIS | 15 | 14 | 1 | 5 |
| General | GEN | 1 | 1 | 0 | 1 |
| **Tổng** | | **73** | **54** | **19** | **26** |

- **Type** `web`: chỉ nội dung trang (Selenium); `native`: có UI của browser / dialog Windows (pywinauto).
- **Sanity**: thuộc lượt kiểm tra nhanh (`python run.py --sanity`).
- **Kết quả**: lần chạy gần nhất trong `artifacts/runs/` của máy sinh file này.

Chạy theo feature: `python run.py --feature bookmarks` · theo case: `python run.py --case BM-101,DL-104`.

## Add-ons (ADD) - 19 case

| ID | Tên | Ưu tiên | Type | Sanity | File | Kết quả |
|---|---|---|---|---|---|---|
| ADD-001 | Installed add-on is listed and active | High | web | ✔ | addons.md | ✅ Pass |
| ADD-002 | Disable an add-on | High | web |  | addons.md | ✅ Pass |
| ADD-003 | Details page | Low | web |  | addons.md | ✅ Pass |
| ADD-010 | Remove an add-on (native confirmation) | High | native |  | addons.md | ✅ Pass |
| ADD-020 | Install an add-on with "Load unpacked" | High | native |  | addons.md | ✅ Pass |
| ADD-022 | Install an add-on from Chrome Web Store | High | native |  | addons.md | ✅ Pass |
| ADD-101 | Card shows name, version, description and source | High | web | ✔ | sanity.md | ✅ Pass |
| ADD-102 | Developer mode shows the developer tools | High | web | ✔ | sanity.md | ✅ Pass |
| ADD-103 | Search add-ons | Low | web |  | sanity.md | ✅ Pass |
| ADD-104 | Disabled state is kept after restart | High | web | ✔ | sanity.md | ✅ Pass |
| ADD-105 | Cancel removal keeps the add-on | Medium | native |  | sanity.md | ✅ Pass |
| ADD-106 | Open Add-ons from the app menu | Medium | native |  | toolbar.md | ✅ Pass |
| ADD-107 | Keyboard shortcuts page lists the add-on | Low | web |  | sanity.md | ✅ Pass |
| ADD-108 | Pack an add-on into a .crx | Medium | web | ✔ | sanity.md | ✅ Pass |
| ADD-109 | Reload an unpacked add-on | Medium | web |  | sanity.md | ✅ Pass |
| ADD-110 | "Get add-ons" opens the add-on store | Low | web |  | sanity.md | ✅ Pass |
| ADD-111 | Pin and unpin an add-on from the toolbar Add-ons menu | High | native | ✔ | toolbar.md | ✅ Pass |
| ADD-112 | Open the add-on popup from its toolbar icon | High | native | ✔ | toolbar.md | ✅ Pass |
| ADD-113 | Add-on "More options" menu opens the options page | Medium | native |  | toolbar.md | ✅ Pass |

<details><summary><b>ADD-001</b> Installed add-on is listed and active</summary>

**Precondition:** "SB Sample Addon" installed (unpacked)

**Steps:**

1. Open the extensions page
2. Open a local test page

**Expected:**

- "SB Sample Addon" is listed and enabled
- The page is marked by the add-on content script

**Nguồn:** `cases/addons/addons.md`  
**Script:** `tests/features/addons/test_addons.py::test_addon_listed_and_active`

</details>

<details><summary><b>ADD-002</b> Disable an add-on</summary>

**Steps:**

1. Turn off "SB Sample Addon" on the extensions page
2. Open a local test page

**Expected:**

- The add-on state is DISABLED; the page is not marked

**Nguồn:** `cases/addons/addons.md`  
**Script:** `tests/features/addons/test_addons.py::test_disable_addon`

</details>

<details><summary><b>ADD-003</b> Details page</summary>

**Steps:**

1. Click Details on "SB Sample Addon"

**Expected:**

- The details view shows the description and version 1.0.0

**Nguồn:** `cases/addons/addons.md`  
**Script:** `tests/features/addons/test_addons.py::test_details_page`

</details>

<details><summary><b>ADD-010</b> Remove an add-on (native confirmation)</summary>

**Steps:**

1. Click Remove on "SB Sample Addon", confirm in the dialog

**Expected:**

- The add-on is gone from the list

**Nguồn:** `cases/addons/addons.md`  
**Script:** `tests/features/addons/test_addons.py::test_remove_addon_native_confirm`

</details>

<details><summary><b>ADD-020</b> Install an add-on with "Load unpacked"</summary>

**Steps:**

1. Open the add-ons page, turn on Developer mode
2. Click "Load unpacked", choose the folder resources/extensions/sample_addon

**Expected:**

- "SB Sample Addon" is listed and enabled

**Nguồn:** `cases/addons/addons.md`  
**Script:** `tests/features/addons/test_addon_install.py::test_load_unpacked`

</details>

<details><summary><b>ADD-022</b> Install an add-on from Chrome Web Store</summary>

**Precondition:** internet through the company proxy; extension id in resources/data/addons.yaml

**Steps:**

1. Open the store page of the extension, click "Add to ..."
2. Confirm "Add extension" in the prompt

**Expected:**

- The store shows the remove button; the add-on is listed on the add-ons page

**Nguồn:** `cases/addons/addons.md`  
**Script:** `tests/features/addons/test_addon_install.py::test_install_from_web_store`

</details>

<details><summary><b>ADD-101</b> Card shows name, version, description and source</summary>

**Precondition:** "SB Sample Addon" 1.0.0 installed (unpacked)

**Steps:**

1. Open Add-ons
2. Turn on Developer mode

**Expected:**

- The card shows "SB Sample Addon", the manifest description, Details and Remove; the switch is on
- With Developer mode on the card also shows the version "1.0.0"

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_card_details`

</details>

<details><summary><b>ADD-102</b> Developer mode shows the developer tools</summary>

**Steps:**

1. Open Add-ons, turn on "Developer mode" in the side bar
2. Turn it off again

**Expected:**

- On: the toolbar shows Load Unpacked, Pack add-on, Update
- Off: they are hidden

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_developer_mode_toolbar`

</details>

<details><summary><b>ADD-103</b> Search add-ons</summary>

**Precondition:** "SB Sample Addon" installed

**Steps:**

1. Type "Sample" in the search box, then "zzz"

**Expected:**

- "Sample" lists the add-on; "zzz" lists nothing

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_search`

</details>

<details><summary><b>ADD-104</b> Disabled state is kept after restart</summary>

**Precondition:** "SB Sample Addon" installed

**Steps:**

1. Turn the add-on off
2. Close and reopen the browser on the same profile, open Add-ons

**Expected:**

- The add-on is still off and does not run on pages

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_disabled_survives_restart`

</details>

<details><summary><b>ADD-105</b> Cancel removal keeps the add-on</summary>

**Precondition:** "SB Sample Addon" installed

**Steps:**

1. Click Remove on the card
2. In "Delete SB Sample Addon?" click Cancel

**Expected:**

- The add-on is still installed and enabled

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_cancel_remove`

</details>

<details><summary><b>ADD-106</b> Open Add-ons from the app menu</summary>

**Steps:**

1. Open the app menu (⋮ "Samsung Browser"), click "Add-ons"

**Expected:**

- The Add-ons page opens

**Nguồn:** `cases/addons/toolbar.md`  
**Script:** `tests/features/addons/test_addons_toolbar.py::test_open_from_app_menu`

</details>

<details><summary><b>ADD-107</b> Keyboard shortcuts page lists the add-on</summary>

**Precondition:** "SB Sample Addon" installed

**Steps:**

1. Add-ons > Keyboard shortcuts (side bar)

**Expected:**

- "Activate add-on for SB Sample Addon" is listed with "Not set" and an Edit button

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_keyboard_shortcuts`

</details>

<details><summary><b>ADD-108</b> Pack an add-on into a .crx</summary>

**Steps:**

1. Developer mode on, toolbar "Pack add-on"
2. Enter the root directory of a copy of the sample add-on, click "Pack extension"

**Expected:**

- The dialog asks for the extension root directory and an optional private key file; "Pack extension" is disabled while the directory is empty
- <folder>.crx and <folder>.pem are created next to the folder

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_pack_creates_crx`

</details>

<details><summary><b>ADD-109</b> Reload an unpacked add-on</summary>

**Precondition:** "SB Sample Addon" installed (unpacked), Developer mode on

**Steps:**

1. Click the reload icon on the card
2. Open a local page

**Expected:**

- The add-on stays enabled and its content script still runs

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_reload_unpacked`

</details>

<details><summary><b>ADD-110</b> "Get add-ons" opens the add-on store</summary>

**Steps:**

1. Click "Get add-ons" under the list

**Expected:**

- A new tab opens the Chrome Web Store extensions page

**Nguồn:** `cases/addons/sanity.md`  
**Script:** `tests/features/addons/test_addons_sanity.py::test_get_addons_opens_store`

</details>

<details><summary><b>ADD-111</b> Pin and unpin an add-on from the toolbar Add-ons menu</summary>

**Precondition:** "SB Sample Addon" installed

**Steps:**

1. Click the toolbar "Add-ons" (puzzle) button
2. Click "Pin" next to "SB Sample Addon"
3. Open the menu again, click "Unpin"

**Expected:**

- The menu lists the add-on with Pin and "More options"
- After Pin the add-on icon is in the toolbar; after Unpin it is gone

**Nguồn:** `cases/addons/toolbar.md`  
**Script:** `tests/features/addons/test_addons_toolbar.py::test_pin_from_addons_menu`

</details>

<details><summary><b>ADD-112</b> Open the add-on popup from its toolbar icon</summary>

**Precondition:** "SB Sample Addon" installed and pinned

**Steps:**

1. Click the add-on icon in the toolbar
2. Click the "Clicked 0" button in the popup

**Expected:**

- The popup opens with "SB Sample Addon" and "Clicked 0"
- The button turns into "Clicked 1" (the popup's script runs)

**Nguồn:** `cases/addons/toolbar.md`  
**Script:** `tests/features/addons/test_addons_toolbar.py::test_popup_from_toolbar_icon`

</details>

<details><summary><b>ADD-113</b> Add-on "More options" menu opens the options page</summary>

**Precondition:** "SB Sample Addon" installed

**Steps:**

1. Toolbar "Add-ons" > "More options" of the add-on
2. Click "Options"

**Expected:**

- The menu offers Options, Remove from Samsung Browser, Manage add-on
- A tab "SB options" opens with "SB Sample Addon options"

**Nguồn:** `cases/addons/toolbar.md`  
**Script:** `tests/features/addons/test_addons_toolbar.py::test_more_options_opens_options_page`

</details>

## Bookmarks (BM) - 22 case

| ID | Tên | Ưu tiên | Type | Sanity | File | Kết quả |
|---|---|---|---|---|---|---|
| BM-001 | Add a bookmark from the bookmark manager | High | web | ✔ | bookmark_manager.md | ✅ Pass |
| BM-002 | Add a folder | High | web |  | bookmark_manager.md | ✅ Pass |
| BM-003 | Edit a bookmark | High | web |  | bookmark_manager.md | ✅ Pass |
| BM-004 | Delete a bookmark and undo | High | web | ✔ | bookmark_manager.md | ✅ Pass |
| BM-005 | Search bookmarks | Medium | web |  | bookmark_manager.md | ✅ Pass |
| BM-006 | Open a sub folder | Medium | web |  | bookmark_manager.md | ✅ Pass |
| BM-101 | Bookmark the page with Ctrl+D and rename it from the toast | High | native | ✔ | toolbar.md | ✅ Pass |
| BM-102 | Remove a bookmark with the star | Medium | native |  | toolbar.md | ✅ Pass |
| BM-103 | Edit name and web address | High | web | ✔ | sanity.md | ✅ Pass |
| BM-104 | Edit from the right-click menu | Medium | web |  | sanity.md | ✅ Pass |
| BM-105 | Delete from the right-click menu and undo | High | web | ✔ | sanity.md | ✅ Pass |
| BM-106 | Select all and delete | Medium | web |  | sanity.md | ✅ Pass |
| BM-107 | Open a bookmark from the manager | High | web | ✔ | sanity.md | ✅ Pass |
| BM-108 | Bookmarks are kept after restarting the browser | High | web | ✔ | sanity.md | ✅ Pass |
| BM-109 | Add a bookmark into a sub folder | High | web |  | sanity.md | ✅ Pass |
| BM-110 | Sort by name | Medium | web |  | sanity.md | ✅ Pass |
| BM-111 | Delete a folder with its bookmarks and undo | High | web | ✔ | sanity.md | ✅ Pass |
| BM-112 | Open all bookmarks of a folder in new tabs | Medium | web |  | sanity.md | ✅ Pass |
| BM-113 | Export bookmarks to an HTML file | Medium | native |  | sanity.md | ✅ Pass |
| BM-114 | "Import bookmarks" opens the import settings | Low | web |  | sanity.md | ✅ Pass |
| BM-115 | Browse the Bookmarks panel and open a bookmark | High | native | ✔ | toolbar.md | ✅ Pass |
| BM-116 | Add the current page from the panel, open the manager with Expand | Medium | native |  | toolbar.md | ✅ Pass |

<details><summary><b>BM-001</b> Add a bookmark from the bookmark manager</summary>

**Precondition:** Clean profile

**Steps:**

1. Open the bookmark manager
2. Open the Organize menu and choose "Add new bookmark"
3. Enter a name and a URL, click Save

**Expected:**

- The new bookmark is listed with the given name

**Nguồn:** `cases/bookmarks/bookmark_manager.md`  
**Script:** `tests/features/bookmarks/test_bookmark_manager.py::test_add_bookmark`

</details>

<details><summary><b>BM-002</b> Add a folder</summary>

**Precondition:** Clean profile

**Steps:**

1. Open the bookmark manager
2. Organize menu > "Add new folder", enter a name, Save

**Expected:**

- The folder is listed in the list and in the folder tree

**Nguồn:** `cases/bookmarks/bookmark_manager.md`  
**Script:** `tests/features/bookmarks/test_bookmark_manager.py::test_add_folder`

</details>

<details><summary><b>BM-003</b> Edit a bookmark</summary>

**Precondition:** Bookmarks bar contains "Static page 1"

**Steps:**

1. Open the bookmark manager
2. Open the item menu of "Static page 1" and choose Edit
3. Change the name to a new value, Save

**Expected:**

- The list shows the new name, the old name is gone

**Nguồn:** `cases/bookmarks/bookmark_manager.md`  
**Script:** `tests/features/bookmarks/test_bookmark_manager.py::test_edit_bookmark`

</details>

<details><summary><b>BM-004</b> Delete a bookmark and undo</summary>

**Precondition:** Bookmarks bar contains "Static page 2"

**Steps:**

1. Open the bookmark manager
2. Delete "Static page 2" from its item menu
3. Click Undo on the toast

**Expected:**

- After step 2 the item is gone and a toast says it was deleted
- After step 3 the item is back

**Nguồn:** `cases/bookmarks/bookmark_manager.md`  
**Script:** `tests/features/bookmarks/test_bookmark_manager.py::test_delete_and_undo`

</details>

<details><summary><b>BM-005</b> Search bookmarks</summary>

**Precondition:** Several bookmarks exist (Alpha, Beta, Gamma, Delta)

**Steps:**

1. Open the bookmark manager
2. Type "ta" in the search box

**Expected:**

- Only "Beta" and "Delta" are listed

**Nguồn:** `cases/bookmarks/bookmark_manager.md`  
**Script:** `tests/features/bookmarks/test_bookmark_manager.py::test_search`

</details>

<details><summary><b>BM-006</b> Open a sub folder</summary>

**Precondition:** Folder "Work" with "Form page" and "Dialogs page"

**Steps:**

1. Open the bookmark manager, select folder "Work" in the tree

**Expected:**

- The list shows exactly "Form page" and "Dialogs page"

**Nguồn:** `cases/bookmarks/bookmark_manager.md`  
**Script:** `tests/features/bookmarks/test_bookmark_manager.py::test_open_folder`

</details>

<details><summary><b>BM-101</b> Bookmark the page with Ctrl+D and rename it from the toast</summary>

**Precondition:** Clean profile; local page "Static page 1"

**Steps:**

1. Open "Static page 1"
2. Press Ctrl+D
3. Click "Edit" on the toast, change the name, Save
4. Open the bookmark manager

**Expected:**

- Step 2: toast "Page bookmarked." with an "Edit" button; the star turns into "Remove from Bookmarks"
- Step 3: the edit bubble shows "Bookmark name" and "Bookmark URL" (address shown without http://)
- Step 4: the bookmark is listed with the new name only

**Nguồn:** `cases/bookmarks/toolbar.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_toolbar.py::test_ctrl_d_toast_and_rename`

</details>

<details><summary><b>BM-102</b> Remove a bookmark with the star</summary>

**Precondition:** "Static page 1" is bookmarked (Ctrl+D)

**Steps:**

1. On "Static page 1" click the filled star in the address bar
2. Open the bookmark manager

**Expected:**

- The star is no longer shown as bookmarked
- "Static page 1" is not listed

**Nguồn:** `cases/bookmarks/toolbar.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_toolbar.py::test_star_removes_bookmark`

</details>

<details><summary><b>BM-103</b> Edit name and web address</summary>

**Precondition:** Bookmark bar contains "Static page 1"

**Steps:**

1. Open the bookmark manager
2. Tick "Static page 1", click Edit in the toolbar
3. Change Name and Web address, click Save

**Expected:**

- The list shows the new name with the new address; the old name is gone

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_edit_name_and_url`

</details>

<details><summary><b>BM-104</b> Edit from the right-click menu</summary>

**Precondition:** Bookmark bar contains "Static page 2"

**Steps:**

1. Open the bookmark manager
2. Right click "Static page 2" > Edit, change the name, Save

**Expected:**

- The right-click menu offers Edit, Delete, Open all (1) in new tab / new window / Secret mode
- The list shows the new name

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_edit_from_context_menu`

</details>

<details><summary><b>BM-105</b> Delete from the right-click menu and undo</summary>

**Precondition:** Bookmark bar contains "Static page 2"

**Steps:**

1. Open the bookmark manager
2. Right click "Static page 2" > Delete
3. Click Undo on the snack bar

**Expected:**

- After step 2 the item is gone and a snack bar says "1 bookmark deleted"
- After step 3 the item is back

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_delete_from_context_menu_and_undo`

</details>

<details><summary><b>BM-106</b> Select all and delete</summary>

**Precondition:** Bookmark bar contains Static page 1, Static page 2 and folder Work

**Steps:**

1. Open the bookmark manager
2. Click "Select all" in the toolbar, then "Delete all"

**Expected:**

- The header shows "3 selected"; the toolbar offers "Delete all" and "Deselect all"
- The list is empty afterwards ("No bookmarks") and the snack bar reports the deletion

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_select_all_and_delete`

</details>

<details><summary><b>BM-107</b> Open a bookmark from the manager</summary>

**Precondition:** Bookmark bar contains "Static page 1"

**Steps:**

1. Open the bookmark manager
2. Click "Static page 1"

**Expected:**

- "Static page 1" opens in a new tab

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_open_bookmark`

</details>

<details><summary><b>BM-108</b> Bookmarks are kept after restarting the browser</summary>

**Precondition:** Clean profile

**Steps:**

1. Create a folder in Bookmark bar and rename a seeded bookmark
2. Close and reopen the browser on the same profile
3. Open the bookmark manager

**Expected:**

- The folder and the renamed bookmark are still listed

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_bookmarks_survive_restart`

</details>

<details><summary><b>BM-109</b> Add a bookmark into a sub folder</summary>

**Precondition:** Bookmark bar contains folder "Work"

**Steps:**

1. Open the bookmark manager, select folder "Work" in the tree
2. Right ⋮ > Add bookmark, enter Name and Web address, Save

**Expected:**

- The bookmark is listed in "Work" with the given address
- It is not listed in Bookmark bar

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_add_bookmark_into_folder`

</details>

<details><summary><b>BM-110</b> Sort by name</summary>

**Precondition:** Bookmark bar contains Alpha, Beta, Gamma, Delta and folder "Folder X" (in that order)

**Steps:**

1. Open the bookmark manager
2. Right ⋮ > Sort by name

**Expected:**

- The order becomes Folder X, Alpha, Beta, Delta, Gamma (folders first, then A-Z)

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_sort_by_name`

</details>

<details><summary><b>BM-111</b> Delete a folder with its bookmarks and undo</summary>

**Precondition:** Folder "Work" contains "Form page" and "Dialogs page"

**Steps:**

1. Tick "Work", click Delete
2. Click Undo on the snack bar

**Expected:**

- After step 1 "Work" is gone from the list and the tree
- After step 2 "Work" is back with both bookmarks inside

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_delete_folder_and_undo`

</details>

<details><summary><b>BM-112</b> Open all bookmarks of a folder in new tabs</summary>

**Precondition:** Folder "Work" contains 2 bookmarks

**Steps:**

1. Right click "Work" > Open all (2) in new tab

**Expected:**

- Two new tabs open: "Form page" and "Dialogs page"

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_open_all_in_new_tabs`

</details>

<details><summary><b>BM-113</b> Export bookmarks to an HTML file</summary>

**Precondition:** Bookmark bar contains Static page 1, Static page 2, Work

**Steps:**

1. Left ⋮ > Export bookmarks
2. In the Windows Save As dialog (default name "bookmarks_<date>", HTML) save to a test folder

**Expected:**

- The HTML file is written and contains the bookmark titles and addresses

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_export_bookmarks`

</details>

<details><summary><b>BM-114</b> "Import bookmarks" opens the import settings</summary>

**Steps:**

1. Left ⋮ > Import bookmarks

**Expected:**

- Settings opens in a new tab on the import page

**Nguồn:** `cases/bookmarks/sanity.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_sanity.py::test_import_opens_settings`

</details>

<details><summary><b>BM-115</b> Browse the Bookmarks panel and open a bookmark</summary>

**Precondition:** Bookmark bar contains Static page 1, Static page 2 and folder Work

**Steps:**

1. Click the toolbar "Bookmarks" button
2. Open "Bookmark bar" in the panel
3. Click "Static page 1"

**Expected:**

- The panel shows the tree "PC bookmarks" > "Bookmark bar" with Add bookmark, Create folder, Expand buttons
- "Bookmark bar" lists Static page 1, Static page 2 and Work
- "Static page 1" opens

**Nguồn:** `cases/bookmarks/toolbar.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_toolbar.py::test_panel_browse_and_open`

</details>

<details><summary><b>BM-116</b> Add the current page from the panel, open the manager with Expand</summary>

**Steps:**

1. Open a page, toolbar "Bookmarks" > "Add bookmark"
2. Open the panel again, click "Expand"

**Expected:**

- Step 1: the page is bookmarked (star filled)
- Step 2: the bookmark manager opens in a tab and finds the page

**Nguồn:** `cases/bookmarks/toolbar.md`  
**Script:** `tests/features/bookmarks/test_bookmarks_toolbar.py::test_panel_add_page_and_expand`

</details>

## Downloads (DL) - 16 case

| ID | Tên | Ưu tiên | Type | Sanity | File | Kết quả |
|---|---|---|---|---|---|---|
| DL-001 | Download a file | High | web | ✔ | downloads.md | ✅ Pass |
| DL-002 | Remove an entry from the list | High | web |  | downloads.md | ✅ Pass |
| DL-003 | Clear all | Medium | web |  | downloads.md | ✅ Pass |
| DL-004 | Pause and resume | Medium | web |  | downloads.md | ✅ Pass |
| DL-010 | Ask where to save -> Save As dialog | Medium | native |  | downloads.md | ✅ Pass |
| DL-101 | Finished download shows name, size and source | High | web | ✔ | sanity.md | ✅ Pass |
| DL-102 | Category filter | Medium | web |  | sanity.md | ✅ Pass |
| DL-103 | Search downloads | Medium | web |  | sanity.md | ✅ Pass |
| DL-104 | Cancel a download in progress | High | web | ✔ | sanity.md | ✅ Pass |
| DL-105 | Open Downloads with Ctrl+J | Medium | native |  | sanity.md | ✅ Pass |
| DL-106 | "Show in folder" opens File Explorer on the file | Medium | native |  | sanity.md | ✅ Pass |
| DL-107 | Remove an entry and undo | Medium | web |  | sanity.md | ✅ Pass |
| DL-108 | Same file downloaded twice gets a new name | High | web | ✔ | sanity.md | ✅ Pass |
| DL-109 | "Copy link" copies the download address | Low | native |  | sanity.md | ✅ Pass |
| DL-110 | Toolbar Downloads bubble lists the finished file | Medium | native |  | sanity.md | ✅ Pass |
| DL-111 | Link with a download attribute saves under that name | Medium | web |  | sanity.md | ✅ Pass |

<details><summary><b>DL-001</b> Download a file</summary>

**Steps:**

1. Open the downloads test page, click "sample.txt"
2. Open the Downloads page

**Expected:**

- The file exists on disk with the right size
- "sample.txt" is listed

**Nguồn:** `cases/downloads/downloads.md`  
**Script:** `tests/features/downloads/test_downloads.py::test_download_file`

</details>

<details><summary><b>DL-002</b> Remove an entry from the list</summary>

**Steps:**

1. Download "sample.txt"; open Downloads
2. Click "Delete from history" on the entry

**Expected:**

- The entry is gone from the list; the file stays on disk

**Nguồn:** `cases/downloads/downloads.md`  
**Script:** `tests/features/downloads/test_downloads.py::test_remove_entry_keeps_file`

</details>

<details><summary><b>DL-003</b> Clear all</summary>

**Steps:**

1. Download two files; open Downloads; click "Clear all"

**Expected:**

- The list is empty

**Nguồn:** `cases/downloads/downloads.md`  
**Script:** `tests/features/downloads/test_downloads.py::test_clear_all`

</details>

<details><summary><b>DL-004</b> Pause and resume</summary>

**Steps:**

1. Start the slow 10 MB download; open Downloads
2. Pause it, then Resume

**Expected:**

- Status shows "Paused" after pause, the download completes after resume

**Nguồn:** `cases/downloads/downloads.md`  
**Script:** `tests/features/downloads/test_downloads.py::test_pause_resume`

</details>

<details><summary><b>DL-010</b> Ask where to save -> Save As dialog</summary>

**Precondition:** Setting "Ask where to save each file" is on

**Steps:**

1. Click "sample.txt" on the downloads page
2. In the Save As dialog enter a new file name, Save

**Expected:**

- The file is saved with the chosen name

**Nguồn:** `cases/downloads/downloads.md`  
**Script:** `tests/features/downloads/test_downloads.py::test_save_as_dialog`

</details>

<details><summary><b>DL-101</b> Finished download shows name, size and source</summary>

**Steps:**

1. Download sample.txt (2 KB) from the local downloads page
2. Open Downloads

**Expected:**

- sample.txt is listed under "Today" with its size (2.05 KB) and source link 127.0.0.1
- The file is in the download folder

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_entry_details`

</details>

<details><summary><b>DL-102</b> Category filter</summary>

**Steps:**

1. Download sample.txt, data.bin and photo.png (image/png)
2. Open Downloads, choose Document, Others, Image, Video in the side bar

**Expected:**

- Document lists sample.txt only, Others data.bin only, Image photo.png only, Video nothing

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_category_filter`

</details>

<details><summary><b>DL-103</b> Search downloads</summary>

**Steps:**

1. Download sample.txt and data.bin
2. Type "data" in the search box

**Expected:**

- Only data.bin is listed

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_search`

</details>

<details><summary><b>DL-104</b> Cancel a download in progress</summary>

**Steps:**

1. Start the slow 10 MB download
2. Open Downloads, click Cancel on the row

**Expected:**

- The row is removed and a snack bar says "slow.bin removed from Downloads." (with Undo)
- The toolbar Downloads bubble shows slow.bin as "Canceled"
- No slow.bin is left in the download folder

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_cancel_in_progress`

</details>

<details><summary><b>DL-105</b> Open Downloads with Ctrl+J</summary>

**Steps:**

1. Press Ctrl+J

**Expected:**

- The Downloads page opens

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_ctrl_j_opens_downloads`

</details>

<details><summary><b>DL-106</b> "Show in folder" opens File Explorer on the file</summary>

**Steps:**

1. Download sample.txt, open Downloads
2. Click the "Show in folder" icon of the row

**Expected:**

- File Explorer opens the download folder with sample.txt selected

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_show_in_folder`

</details>

<details><summary><b>DL-107</b> Remove an entry and undo</summary>

**Steps:**

1. Download photo.png, open Downloads
2. Click X on the row, then Undo on the snack bar

**Expected:**

- After X the row is gone; after Undo it is back

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_remove_and_undo`

</details>

<details><summary><b>DL-108</b> Same file downloaded twice gets a new name</summary>

**Steps:**

1. Download sample.txt twice

**Expected:**

- The folder has sample.txt and "sample (1).txt"; both are listed

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_duplicate_name`

</details>

<details><summary><b>DL-109</b> "Copy link" copies the download address</summary>

**Steps:**

1. Download sample.txt, open Downloads
2. Click the "Copy link" icon of the row

**Expected:**

- The Windows clipboard holds the address the file was downloaded from

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_copy_link`

</details>

<details><summary><b>DL-110</b> Toolbar Downloads bubble lists the finished file</summary>

**Steps:**

1. Download sample.txt from a page

**Expected:**

- The toolbar Downloads bubble opens with "sample.txt 2,048 B • Done"

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_toolbar_bubble`

</details>

<details><summary><b>DL-111</b> Link with a download attribute saves under that name</summary>

**Steps:**

1. Click a link to page1.html that has download="saved-page1.html"

**Expected:**

- saved-page1.html is in the download folder and listed in Downloads

**Nguồn:** `cases/downloads/sanity.md`  
**Script:** `tests/features/downloads/test_downloads_sanity.py::test_download_attribute`

</details>

## History (HIS) - 15 case

| ID | Tên | Ưu tiên | Type | Sanity | File | Kết quả |
|---|---|---|---|---|---|---|
| HIS-001 | Visited pages are listed newest first | High | web | ✔ | history.md | ✅ Pass |
| HIS-002 | Search history | Medium | web |  | history.md | ✅ Pass |
| HIS-003 | Delete selected entries | High | web | ✔ | history.md | ✅ Pass |
| HIS-004 | Remove one entry from its menu | Medium | web |  | history.md | ✅ Pass |
| HIS-005 | Open a page from history | Medium | web |  | history.md | ✅ Pass |
| HIS-010 | Open History with Ctrl+H | Medium | native |  | history.md | ✅ Pass |
| HIS-101 | Entries show title, domain and time under a day header | High | web | ✔ | sanity.md | ✅ Pass |
| HIS-102 | Clear history | High | web | ✔ | sanity.md | ✅ Pass |
| HIS-103 | Time filter | Medium | web |  | sanity.md | ✅ Pass |
| HIS-104 | Delete a whole day | Medium | web |  | sanity.md | ✅ Pass |
| HIS-105 | History is kept after restarting the browser | High | web | ✔ | sanity.md | ✅ Pass |
| HIS-106 | "Clear browsing data" link | Low | web |  | sanity.md | ✅ Pass |
| HIS-107 | Search with no match | Low | web |  | sanity.md | ✅ Pass |
| HIS-108 | Cancel a selection | Low | web |  | sanity.md | ✅ Pass |
| HIS-109 | Visiting a page again moves it to the top | Medium | web |  | sanity.md | ✅ Pass |

<details><summary><b>HIS-001</b> Visited pages are listed newest first</summary>

**Steps:**

1. Visit page "Alpha", then "Beta"
2. Open History

**Expected:**

- "Beta" is listed above "Alpha"

**Nguồn:** `cases/history/history.md`  
**Script:** `tests/features/history/test_history.py::test_visited_pages_listed`

</details>

<details><summary><b>HIS-002</b> Search history</summary>

**Steps:**

1. Visit "Alpha", "Beta", "Gamma"; open History
2. Search "Gam"

**Expected:**

- Only "Gamma" is listed

**Nguồn:** `cases/history/history.md`  
**Script:** `tests/features/history/test_history.py::test_search_history`

</details>

<details><summary><b>HIS-003</b> Delete selected entries</summary>

**Steps:**

1. Visit "Alpha", "Beta"; open History
2. Select "Alpha", click Delete, confirm Remove

**Expected:**

- "Alpha" is gone, "Beta" stays

**Nguồn:** `cases/history/history.md`  
**Script:** `tests/features/history/test_history.py::test_delete_selected`

</details>

<details><summary><b>HIS-004</b> Remove one entry from its menu</summary>

**Steps:**

1. Visit "Alpha"; open History
2. Item menu > "Remove from history"

**Expected:**

- History is empty

**Nguồn:** `cases/history/history.md`  
**Script:** `tests/features/history/test_history.py::test_remove_from_menu`

</details>

<details><summary><b>HIS-005</b> Open a page from history</summary>

**Steps:**

1. Visit "Alpha"; open History; click "Alpha"

**Expected:**

- The page "Alpha" is loaded

**Nguồn:** `cases/history/history.md`  
**Script:** `tests/features/history/test_history.py::test_open_from_history`

</details>

<details><summary><b>HIS-010</b> Open History with Ctrl+H</summary>

**Steps:**

1. Press Ctrl+H

**Expected:**

- A tab with the History page is opened

**Nguồn:** `cases/history/history.md`  
**Script:** `tests/features/history/test_history.py::test_ctrl_h_opens_history`

</details>

<details><summary><b>HIS-101</b> Entries show title, domain and time under a day header</summary>

**Precondition:** Clean profile

**Steps:**

1. Visit Alpha, then Beta (local pages)
2. Open History

**Expected:**

- Beta is above Alpha
- Each entry shows its domain (127.0.0.1) and a visit time
- The entries are grouped under "Today - <date>"

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_entry_details`

</details>

<details><summary><b>HIS-102</b> Clear history</summary>

**Precondition:** Some pages visited

**Steps:**

1. Open History
2. Click "Clear history" in the toolbar and confirm

**Expected:**

- The list is empty

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_clear_history`

</details>

<details><summary><b>HIS-103</b> Time filter</summary>

**Precondition:** Pages visited just now

**Steps:**

1. Open History
2. Tick only "Last hour"; then only "Yesterday"; then "Yesterday" + "Today"; then "All time"

**Expected:**

- The time filters are check boxes; several ranges can be ticked and add up
- Last hour, Yesterday + Today and All time list the pages; Yesterday alone does not

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_time_filter`

</details>

<details><summary><b>HIS-104</b> Delete a whole day</summary>

**Precondition:** Alpha and Beta visited today

**Steps:**

1. Open History
2. Tick the "Today - <date>" check box, click Delete

**Expected:**

- Both entries are gone

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_delete_whole_day`

</details>

<details><summary><b>HIS-105</b> History is kept after restarting the browser</summary>

**Steps:**

1. Visit Alpha
2. Close and reopen the browser on the same profile
3. Open History

**Expected:**

- Alpha is listed

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_history_survives_restart`

</details>

<details><summary><b>HIS-106</b> "Clear browsing data" link</summary>

**Steps:**

1. Open History, click "Clear browsing data" in the side bar

**Expected:**

- Settings > Clear browsing data opens

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_clear_browsing_data_link`

</details>

<details><summary><b>HIS-107</b> Search with no match</summary>

**Steps:**

1. Visit Alpha, open History
2. Search "zzzz"

**Expected:**

- No entry is listed

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_search_no_match`

</details>

<details><summary><b>HIS-108</b> Cancel a selection</summary>

**Steps:**

1. Tick Alpha (the toolbar switches to "1 selected")
2. Click "<" (Cancel)

**Expected:**

- No entry is ticked; Delete is disabled again

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_cancel_selection`

</details>

<details><summary><b>HIS-109</b> Visiting a page again moves it to the top</summary>

**Steps:**

1. Visit Alpha, Beta, then Alpha again
2. Open History

**Expected:**

- Alpha is listed above Beta

**Nguồn:** `cases/history/sanity.md`  
**Script:** `tests/features/history/test_history_sanity.py::test_revisit_moves_to_top`

</details>

## General (GEN) - 1 case

| ID | Tên | Ưu tiên | Type | Sanity | File | Kết quả |
|---|---|---|---|---|---|---|
| GEN-001 | Back and forward navigation | High | web | ✔ | general.md | ✅ Pass |

<details><summary><b>GEN-001</b> Back and forward navigation</summary>

**Steps:**

1. Open "Static page 1", follow the link to "Static page 2"
2. Go back, then forward

**Expected:**

- Titles follow page 1 -> page 2 -> page 1 -> page 2

**Nguồn:** `cases/general/general.md`  
**Script:** `tests/features/general/test_navigation.py::test_back_forward`

</details>
