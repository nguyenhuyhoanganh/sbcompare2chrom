# Feature notes (what works, what bites)

Upstream bullets: Chromium 141 WebUI. **Samsung** bullets: Samsung Browser 31.0.0.55
(Chromium 148, Windows arm64), verified by the sanity suite (`testcases/<feature>/sanity.md`).

## Samsung Browser - whole product

- WebDriver URLs are `chrome://...` (`pages.scheme: chrome`); the address bar *shows*
  `internet://...` (`pages.display_scheme`, `cfg.display_url(name)` for omnibox asserts).
  `driver.get("internet://...")` does nothing.
- chromedriver cannot launch the exe (hangs on DevTools) -> target uses `browser.mode: attach`.
- Fresh profiles show a "Samsung Browser has been updated." bubble: the `native` fixture closes
  it (`startup_bubbles` in `config/native_ui/samsung.yaml`). Web-only tests are not affected.
- Native bubbles fade in and ignore UIA Invoke while animating: `Dialog.click()` waits and uses
  the real mouse for Views buttons. Bubbles with no title are found by a Text inside.
- Internal pages share `si-*` components: toolbar buttons (`page.toolbar("Delete")`),
  snack bar (`page.wait_toast("deleted")`), `si-dialog`, right-click `si-action-menu`,
  left side bar with search + filters (`page.side_bar("Image")`).

## Bookmarks (`internet://bookmarks`, prefix BM)

- Seed with `@pytest.mark.browser(bookmarks=...)`. Root "Bookmarks bar" is selected on open.
- Folder tree is collapsed by default: `open_folder()` / `folders()` call `expand_tree()`.
- Row menu (⋮): Edit, Copy URL, Delete, Open in new tab/window/incognito, Show in folder (search results).
- Organize menu (toolbar ⋮): Sort by name, Add new bookmark, Add new folder, Import, Export.
- Delete -> toast "'Name' deleted" + Undo. Undo restores the same position.
- Multi-select: `select("A", "B")` (Ctrl+click) then `delete_selected()`; Ctrl+A / Delete
  keys work via `web.press` while the list has focus.
- Import/Export open OS file dialogs -> native `file_dialog("open"/"save")`; import file:
  `files.bookmarks_html(...)`.
- Bookmark star / Ctrl+D / bookmarks bar are native UI. Bookmarks bar visibility pref:
  `bookmark_bar.show_on_all_tabs`.
- Drag & drop inside the manager uses Chromium's own drag API: `method="native"` is the
  reliable option on Windows; `html5` synthesized events are often ignored there.
- Chrome on Windows: Ctrl+D saves to "Other bookmarks" while the bookmarks bar is hidden -
  find the new bookmark with `search()`.
- **Samsung**: roots "PC bookmarks" > "Bookmark bar"; tree is expanded. Rows have a round check
  box; Edit / Share / Delete / Select all are toolbar buttons acting on the selection ("Delete
  all" / "Deselect all" when everything is selected). Right click a row: Edit, Delete, Open all
  (n) in new tab / new window / Secret mode. Right ⋮: Add bookmark (`add_bookmark`, same dialog
  as Edit), Sort by name (folders first), Open all. Left ⋮: Create folder in selected folder,
  Sort by name, Import bookmarks (opens Settings in a new tab), Export bookmarks (Save As, HTML:
  `export(native, path)`).
  "Create folder" adds "Folder N" in the selected folder, opens it and edits its name in the tree
  (`add_folder(name)` types over it). Delete is immediate: snack bar "1 bookmark deleted" + Undo.
  Clicking a bookmark opens it in a NEW TAB.
- **Samsung** toolbar "Bookmarks" button -> panel: header buttons Add bookmark (adds the current
  page), Create folder, Expand (opens the manager); tree "PC bookmarks" > "Bookmark bar" (folders
  are Buttons `auto_id=folder`, bookmarks are TreeItems). Ui-map keys `bookmarks_panel_*`.
- **Samsung** toast "Edit" -> edit bubble: Edits "Bookmark name" / "Bookmark URL" (URL shown
  without `http://`), "Create folder in selected folder", Save / Cancel. Toast text is "Page
  bookmarked." or "Bookmark added to <folder>" (page already bookmarked elsewhere).
- **Samsung** Ctrl+D bookmarks at once: toast "Page bookmarked." [Edit] (`dialogs.bookmark_added`),
  star becomes `StarView` "Remove from Bookmarks"; clicking it removes the bookmark. The toast
  can cover the star: `native.click("bookmark_star", real_mouse=False)`.

## History (`internet://history`, prefix HIS)

- Seed by visiting `site.page(title)`; wait for the title before the next visit.
- Entries are newest first, grouped by day; `rows()` reads them in one call.
- Delete selected -> confirmation `cr-dialog` ("Remove" / "Cancel") handled by `delete_selected()`.
- "Delete browsing data" opens settings (new tab in upstream) -> `web.wait_new_tab(before)`.
- Search is debounced; wait on the result (`web.wait_until(lambda: h.titles() == [...])`).
- Ctrl+H is a browser shortcut -> native. Samsung opens a new tab; Chrome reuses a blank tab:
  `web.switch_tab(url=cfg.page_url("history"))`.
- **Samsung**: each row has a round check box (`select()`), the day header has its own
  (`#all-select`). Toolbar: Share, Delete (no confirmation), Clear history. Side bar time
  filters are CHECK BOXES (several ranges add up): `filter_time("Last hour")` leaves exactly
  the given ones ticked. "Clear browsing data" -> settings `clearBrowserData`.

## Downloads (`internet://downloads`, prefix DL)

- The session downloads into its own folder (`downloads_dir`); prompt is off by default.
  Turn on Save As with `browser(prefs={"download.prompt_for_download": True})` + native `file_dialog`.
- Completed row shows `#file-link`; in-progress shows `#name` + progress -> `info()` handles both.
- Pause/Resume/Cancel are in the row ⋮ menu (`action(name, "Pause")`), quick buttons by
  aria-label ("Show in folder", "Delete from history", "Copy download link").
- "Show in folder"/"Open" launch Explorer / the default app (outside the browser): assert
  with `native` only if really required and close the window afterwards.
- Download bubble/toolbar icon is native (`downloads_button`, dialog `download_bubble`).
- Dangerous/blocked file types show a warning instead of finishing - pick safe types.
- **Samsung**: side bar search + categories (All, Image, Video, Audio, Document, Others:
  `filter_category()`). Finished row: name, size ("2.05 KB"), source link, icons "Copy link",
  "Show in folder", X (remove, snack bar + Undo). In-progress row: progress bar + text buttons
  Pause/Resume, Cancel (`action(name, "Pause")`). Cancel REMOVES the row ("x removed from
  Downloads." + Undo); the toolbar Downloads bubble shows "Canceled". Toolbar: "Clear download
  history". A finished download opens the toolbar bubble over the page.

## Settings (`internet://settings`, prefix SET)

- Sections: `open_section("downloads"|"onStartup"|"appearance"|"search"|"privacy"|"clearBrowserData"...)`.
- Toggles: by visible label = `cr-toggle[aria-label]`: `set_toggle(label, True)`, `is_on(label)`.
- Radios: `choose_radio(label)`; dropdowns: `choose(label, option)` (native `<select>` with aria-label).
- Always cross-check with `get_pref(...)`; persistence: `session.restart()` then reopen
  (`SettingsPage(session.web)` - page objects hold the old `web`).
- Search results are filtered sections: wait for the control you expect.
- Some subpages open `cr-dialog`s (Clear browsing data, Add search engine): `open_dialog()`,
  `dialog_button("Delete data")`.

## Add-ons (`internet://extensions`, prefix ADD)

- **Samsung**: page title "Add-ons". Developer mode is a toggle in the LEFT side bar; on, the
  toolbar shows Load Unpacked, Pack add-on, Update and cards show the version. Card buttons
  Details / Remove (si-flat-button). Remove -> native bubble 'Delete <name>?' [Remove] [Cancel].
  Install prompt (store and .crx drop) -> 'Add "<name>"?' [Add] [Not now]; the store also shows
  Google's "Switch to Chrome?" bubble (ignore it). App menu has "Add-ons".
- Store installs: free, popular extensions only (Dark Reader in `test_data/addons.yaml`).
- **Samsung** toolbar "Add-ons" (puzzle, `ExtensionsToolbarButton`) -> menu: each add-on with
  "Pin <name>" / "Unpin <name>" and "More options for <name>" (menu: Options, Remove from Samsung
  Browser, Manage add-on, View web permissions). Pinned icon = `ToolbarActionView` named
  "<name>\nHas access to this site"; its popup is a Document readable through UIA.
- "Options" opens the add-on's options page in a BACKGROUND tab: WebDriver cannot read that
  chrome-extension:// tab (renderer timeout) - check `native.tab_titles()`, bring it to front by
  clicking its TabItem and read it with `native.wait_text(...)`.

- Load with `browser(extensions=["sample_addon"])` (unpacked). `info()` returns state from
  `chrome.developerPrivate` (`ENABLED`/`DISABLED`).
- Prove an add-on is active through its effect on a page (content script attribute),
  not only through the toggle.
- Remove -> native confirmation dialog (upstream) -> `native.wait_dialog("remove_extension")`.
- Details: `open_details(name)` -> URL `?id=...`; read with `web.wait_page_text`.
- Install flows (all native):
  - Load unpacked: `pages.extensions.load_unpacked(native, folder)` (dev mode, button, Windows folder picker).
  - Drop .crx: `pages.extensions.drop_crx(native, crx)` - real drag from File Explorer; synthetic
    JS/CDP drops are ignored by the browser (verified on Chromium). Needs developer mode.
    `test_data/extensions/sample_addon.crx` is packed from `sample_addon/`.
  - Web Store: `pages.webstore.install(ext_id, native)` - through the company proxy; button
    text from config `webstore.add_button_texts`; then the native "Add extension" prompt.
  - Data: `test_data/addons.yaml` (`sample`, `webstore` ids).
- Off-store .crx installs can be blocked by policy on branded builds - if the prompt never
  shows, check `internet://policy` and report it rather than working around it.
- Toolbar puzzle icon / pin / popup are native; a popup page can be opened directly in
  a tab: `web.open(f"chrome-extension://{ext_id}/popup.html")`.

## General browsing (prefix GEN)

- Tabs opened by the page: capture `before = web.tabs` first, then `web.wait_new_tab(before)`.
- `window.open` popups are windows; they also appear in `web.tabs`.
- `beforeunload` "Leave site?" is accepted automatically by chromedriver (WebDriver spec): the
  prompt can't be observed or dismissed; cases about it are not automatable with this stack.
- `window.print()` opens print preview (browser UI) -> native; close with `{ESC}`.
- Permission prompts (notifications, location) are native bubbles.
