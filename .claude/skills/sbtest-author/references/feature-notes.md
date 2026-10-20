# Feature notes (what works, what bites)

Verified against upstream Chromium 141 WebUI. Samsung rewrote many of these pages - confirm with
the `dom` / `uia_dump` tools on the real build and update page objects.

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

## History (`internet://history`, prefix HIS)

- Seed by visiting `site.page(title)`; wait for the title before the next visit.
- Entries are newest first, grouped by day; `rows()` reads them in one call.
- Delete selected -> confirmation `cr-dialog` ("Remove" / "Cancel") handled by `delete_selected()`.
- "Delete browsing data" opens settings (new tab in upstream) -> `web.wait_new_tab(before)`.
- Search is debounced; wait on the result (`web.wait_until(lambda: h.titles() == [...])`).
- Ctrl+H is a browser shortcut -> native.

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

## Settings (`internet://settings`, prefix SET)

- Sections: `open_section("downloads"|"onStartup"|"appearance"|"search"|"privacy"|"clearBrowserData"...)`.
- Toggles: by visible label = `cr-toggle[aria-label]`: `set_toggle(label, True)`, `is_on(label)`.
- Radios: `choose_radio(label)`; dropdowns: `choose(label, option)` (native `<select>` with aria-label).
- Always cross-check with `get_pref(...)`; persistence: `session.restart()` then reopen
  (`SettingsPage(session.web)` - page objects hold the old `web`).
- Search results are filtered sections: wait for the control you expect.
- Some subpages open `cr-dialog`s (Clear browsing data, Add search engine): `open_dialog()`,
  `dialog_button("Delete data")`.

## Add-ons (`internet://extensions`, prefix ADD) - Samsung's own page, re-verify selectors

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
