# Action catalogue - "the request says" -> "the test does"

Verified on Samsung Browser 31.0.0.55 (Chromium 148). Fixtures: `web`, `native`, `pages`,
`site`, `session`, `cfg`, `downloads_dir`, `data`, `tmp_path`.
Logical names in quotes (`"bookmarks_button"`) are keys of `config/native_ui.yaml`;
`name=` fills their `{name}` placeholder. Anything missing here: explore it (SKILL.md step 2)
and add a page-object method or ui-map entry, then add a row to this table.

## Contents

- Preconditions (before the browser starts)
- Pages and navigation
- Bookmarks - manager page (`pages.bookmarks`)
- Bookmarks - browser UI (native)
- History (`pages.history`)
- Downloads (`pages.downloads`, files in `downloads_dir`)
- Add-ons
- Dialogs, bubbles, files
- Reading and asserting
- After writing

## Preconditions (before the browser starts)

| Request / precondition | Do |
|---|---|
| "bookmarks A, B and folder Work exist" | `@pytest.mark.browser(bookmarks="seed_basic")` (sets in `resources/data/bookmarks.yaml`; add one if needed) |
| "add-on X installed" | `@pytest.mark.browser(extensions=["sample_addon"])` (folders in `resources/extensions/`) |
| a setting already on | `@pytest.mark.browser(prefs={"download.prompt_for_download": True})` |
| "pages visited" (history) | `web.open(site.page("Alpha")); web.wait_title("Alpha")` per page |
| "file downloaded" | `web.open(site.url("/downloads.html")); web.click("#dl-txt"); web.wait_file(downloads_dir, "sample.txt")` (`#dl-bin`, `#dl-png`, `#dl-slow`, `#dl-attr`) |
| a local file to upload / import | `files.text_file(tmp_path, "a.txt")`, `files.png_file(...)`, `files.bookmarks_html(...)` |
| unique names | `unique("Folder")` |
| touches browser UI or OS dialogs | `@pytest.mark.native` |

## Pages and navigation

| Request | Do |
|---|---|
| open a web page | `web.open(site.page("Title"))`, `web.open(site.url("/form.html"))` |
| open Bookmarks / History / Downloads / Add-ons page | `pages.bookmarks.open()` / `pages.history.open()` / `pages.downloads.open()` / `pages.extensions.open()` |
| type an address in the address bar | `native.navigate("internet://history")` (user-visible scheme works there) |
| read the address bar | `native.omnibox_text()` (Samsung shows `internet://`; compare with `cfg.display_url("history")`) |
| back / forward / reload / home | `native.click("back_button")` / `"forward_button"` / `"reload_button"` / `"home_button"` |
| keyboard shortcut (Ctrl+D/H/J/T/W/L, F5...) | `native.hotkey("^d")` - never `web.press` for browser shortcuts |
| Enter / Esc / Ctrl+A inside a page | `web.press("ENTER")`, `web.press(Keys.CONTROL, "a")` |
| iframe content | `with web.frame("#frame"): ...` |
| navigation that stops at a browser prompt (HTTP sign-in) | `web.open(url, blocking=False)`, then `native.wait_dialog("http_auth")` |
| something opens "in a tab" | `web.switch_tab(url=cfg.page_url("history"))` or `web.switch_tab(title="X")` (new tab or same tab) |
| new tab expected | `before = web.tabs` ... `web.wait_new_tab(before)` |
| tab opened in the background (extension pages) | `"X" in native.tab_titles()`, then `native.click({"control_type": "TabItem", "title": "X"})`, read with UIA (`native.wait_text("^...$")`) |
| app menu > item | `native.menu("Add-ons")`, `native.menu("History", "History")` |
| restart and check it persisted | `session.restart(); pages.of(session.web).bookmarks.open()` |

## Bookmarks - manager page (`pages.bookmarks`)

| Request | Do |
|---|---|
| list / check an entry | `bm.titles()`, `bm.wait_item("X")`, `bm.wait_item("X", present=False)`, `bm.item_url("X")` |
| open a folder | `bm.open_folder("Work")`, root: `bm.open_folder(bm.BAR_FOLDER)`; tree: `bm.folders()` |
| add a bookmark | `bm.add_bookmark(name, url)` (right ⋮ > Add bookmark, into the open folder) |
| add a folder | `bm.add_folder(name)` (Create folder + rename in the tree) |
| edit name / address | `bm.edit("X", name=..., url=...)` (tick + toolbar Edit) |
| right-click menu | `bm.item_menu("X", "Edit" / "Delete" / "Open all (2) in new tab")` |
| delete + snack bar + undo | `toast = bm.delete("X")` ("1 bookmark deleted"), `bm.undo()` |
| select several / all | `bm.select("A", "B")`, `bm.toolbar("Select all")`, `bm.delete_selected()` ("Delete all") |
| sort / options menu | `bm.options("Sort by name")` (right ⋮), `bm.organize("Import bookmarks")` (left ⋮) |
| open a bookmark | `bm.open_item("X")` (new tab on Samsung, switched to) |
| search | `bm.search("ta")`, `bm.wait_titles([...])` |
| export to a file | `bm.export(native, tmp_path / "b.html")` (Save As) |

## Bookmarks - browser UI (native)

| Request | Do |
|---|---|
| Ctrl+D -> toast "Page bookmarked." / "Bookmark added to ..." | `native.hotkey("^d"); toast = native.wait_dialog("bookmark_added")` |
| toast > Edit -> rename | `toast.click("Edit")`, field `native.element("bookmark_edit_name", in_main=False)` (focus, `native.hotkey("^a", focus=False)`, `native.type_text(...)`), `native.click("bookmark_edit_save")` |
| is the page bookmarked (star) | `native.focus_page()` first (no star while the omnibox has focus; it takes the focus back when a toast closes - wait for the star, refocusing: BM-114), then `native.exists("bookmark_star_filled")` |
| remove with the star | `native.wait_dialog_gone("bookmark_added")` (while the toast shows, a click on the star only closes it), then `native.click("bookmark_star_filled")` |
| Bookmarks panel (toolbar) | `native.click("bookmarks_button")`; folder `native.click("bookmarks_panel_folder", name="Bookmark bar")`; bookmark `native.click("bookmarks_panel_item", name="X")`; buttons `"bookmarks_panel_add_page"`, `"bookmarks_panel_create_folder"`, `"bookmarks_panel_expand"` (opens the manager) |

## History (`pages.history`)

| Request | Do |
|---|---|
| entries, order, details | `h.titles()`, `h.rows()` -> `{title, url, domain, time, day}`, `h.days()` |
| open an entry | `h.open_item("Alpha")` (same tab) |
| select / delete / cancel | `h.select("A", "B")`, `h.delete_selected()`, `h.remove("A")`, `h.cancel_selection()` |
| delete a day | `web.click(web.find("deep=#all-select", within=h.items()[0]))` + `h.delete_selected()` |
| clear history | `h.clear_history()` |
| time filter (check boxes, add up) | `h.filter_time("Last hour")`, `h.filter_time("Yesterday", "Today")`, `h.time_filters()` |
| search | `h.search("Gam")`; empty: `web.wait_until(lambda: not h.titles())` |
| toolbar button state | `h.toolbar_enabled("Delete")` |

## Downloads (`pages.downloads`, files in `downloads_dir`)

| Request | Do |
|---|---|
| row details | `d.wait_complete("x")` -> `{name, url, size, description, tag, in_progress}`, `d.names()` |
| file on disk | `web.wait_file(downloads_dir, "x")` |
| pause / resume / cancel | `d.action("slow.bin", "Pause" / "Resume" / "Cancel")`, `d.status("slow.bin")` ("Paused ...") |
| remove + undo | `d.remove("x")`, `d.toast_action("Undo")` |
| clear the list ("Clear all" = toolbar "Clear download history") | `native.close_download_bubble()` if a download just finished, then `d.clear_all()` |
| category / search | `d.filter_category("Image")`, `d.search("data")` |
| copy link | `d.action("x", "Copy link")` + `pywinauto.clipboard.GetData()` |
| show in folder | `d.action("x", "Show in folder")`, `native.wait_explorer(downloads_dir.name)`, `native.explorer_has_selected(win, "x")` |
| toolbar download bubble | `native.element("download_bubble_item", title_re=r"^x ")` -> name "x 2,048 B • Done" |
| close the download bubble (155+: it covers "Clear download history") | `native.close_download_bubble()` (its X) |
| ask where to save | prefs `download.prompt_for_download` + `native.file_dialog("save").save_as(path)` |

## Add-ons

| Request | Do |
|---|---|
| card / state | `e = pages.extensions.open()`, `e.names()`, `e.item("X")`, `e.is_enabled("X")`, `e.info()` (id, version, state) |
| turn on/off | `e.set_enabled("X", False)` |
| add-on works on a page | sample add-on marks pages: `web.js("return document.documentElement.getAttribute('data-sb-addon')") == "active"` |
| developer mode / tools | `e.set_dev_mode(True)`, `e.dev_toolbar()` -> Load Unpacked, Pack add-on, Update |
| details / shortcuts | `e.open_details("X")`, `e.open_shortcuts()`, `e.shortcuts()` |
| remove (+ cancel) | `e.click_remove("X")`, `dlg = native.wait_dialog("remove_extension")` ("Delete X?"), `dlg.click("Remove" / "Cancel")` |
| install: unpacked / store | `e.load_unpacked(native, folder)`, `pages.webstore.install(id, native)` (free add-ons only) |
| pack | `e.open_pack_dialog()`, `e.pack_inputs()`, `e.pack_button_enabled()`, `e.pack(folder)` |
| store link | `e.get_addons()` (new tab, Chrome Web Store) |
| toolbar Add-ons menu | `native.click("extensions_button")`; pin `native.click("addons_menu_pin", name="X")`, unpin `"addons_menu_unpin"`, more `"addons_menu_more"` + `native.menu_items()` / `native.select_menu_items("Options")` |
| pinned icon -> popup | `native.click("extension_action", name="X")`; popup content via UIA: `native.element({"auto_id": "count"}, in_main=False)` |

## Dialogs, bubbles, files

| Request | Do |
|---|---|
| a browser bubble / prompt | `dlg = native.wait_dialog("<ui-map dialogs key>" or "(?i)regex")` -> `.texts()`, `.click("Label")`, `.click_any("A", "B")`, `.wait_closed()` |
| wait until a bubble / toast is gone (before clicking what it is anchored to) | `native.wait_dialog_gone("bookmark_added")` |
| dialog inside an internal page | `page.open_dialog()`, `page.dialog_text()`, `page.dialog_input("name")`, `page.dialog_button("Save")` |
| upload through Windows Open | `web.click(button)`, `native.file_dialog("open").open(f1, f2)` |
| upload through `<input type=file>` | `web.upload(loc, path)` (no OS dialog) |
| Save As | `native.file_dialog("save").save_as(path)` |
| choose a folder | `native.file_dialog("open").select_folder(path)` |
| drag a file from Explorer | `native.drag_file_from_explorer(path, web=web, target="#drop-zone")` |
| JS alert / confirm / prompt | `web.accept_alert(prompt_text=...)`, `web.dismiss_alert()` |
| "Leave site?" (beforeunload) | not observable: chromedriver accepts it -> `Automated: no (WebDriver auto-accepts beforeunload)` |
| drag & drop inside a page | `web.drag_and_drop(a, b, method="html5" / "actions" / "native")` |
| Windows notification | `native.wait_os_toast("(?i)text")` |
| print preview | `native.wait_dialog("print")`, `.press("{ESC}")` (the page is blocked meanwhile: no `web.*`) |
| right-click on a page | `native.context_menu_web(web, "#next", "Open in new tab")` - Samsung labels: Open in new tab / new window / Secret mode / side panel, Save link as, Copy link (GEN-002) |

## Reading and asserting

| Request | Do |
|---|---|
| text on a page | `web.text(loc)`, `web.wait_text(loc, "x")`, `web.wait_page_text("x")` |
| element state | `web.exists(loc)`, `web.is_checked(loc)`, `web.is_enabled(loc)`, `web.attr(loc, "x")` |
| any text in the browser UI | `native.wait_text("(?i)regex")`, `native.exists("<key>")` |
| wait for something | `web.wait_until(lambda: ..., message="what we wait for")` |
| step + expected for the report | `with step("2. Do X", expected="Y happens"):` |

## After writing

- `- Automated: tests/features/...::test_x` under the case; `python -m sbtest.tools.coverage`.
- New UI names -> `config/native_ui.yaml` with a comment; new selectors -> the page
  object class + its STATUS docstring; new behaviour -> `.agents/skills/sbtest-author/references/feature-notes.md`.
- Add the row you needed to this catalogue.
