# Feature notes (what works, what bites)

Verified by the sanity suite (`cases/<feature>/sanity.md`, `toolbar.md`) on Samsung Browser
31.0.0.55 (Chromium 148, Windows arm64); notes that say "155" come from build 155. Re-check
after a Samsung/Chromium update and record what changed here.

## Contents

- Whole product
- Bookmarks (`internet://bookmarks`, prefix BM)
- History (`internet://history`, prefix HIS)
- Downloads (`internet://downloads`, prefix DL)
- Add-ons (`internet://extensions`, prefix ADD)
- General browsing (prefix GEN)

## Whole product

- WebDriver URLs are `chrome://...` (`pages.scheme: chrome`); the address bar *shows*
  `internet://...` (`pages.display_scheme`, `cfg.display_url(name)` for omnibox asserts).
  `driver.get("internet://...")` does nothing; typing it in the omnibox (`native.navigate`) works.
- chromedriver cannot launch the exe (hangs on DevTools) -> `browser.mode: attach` (default).
- Fresh profiles show a "Samsung Browser has been updated." bubble: the `native` fixture closes
  it (`startup_bubbles` in `config/native_ui.yaml`). Web-only tests are not affected.
- Chromium drops clicks on a bubble's buttons for the double-click time after it shows, and Views
  buttons ignore UIA Invoke: `Dialog.click()` waits out that time (counted from when the dialog
  was found) and uses the real mouse. Every native click first waits until the element is
  enabled, on screen and no longer moving (`uia.wait_actionable`) - no sleeps needed.
- A click on the button a bubble/toast is anchored to (the star under "Page bookmarked.") only
  closes the bubble: `native.wait_dialog_gone("bookmark_added")` first.
- Bubbles with no title are found by a Text inside.
- Terms used in these skills: **snack bar** = the in-page si-snack-bar ("1 bookmark deleted"
  [Undo], `page.wait_toast`); **toast** = the native browser toast ("Page bookmarked." [Edit],
  `native.wait_dialog`); **bubble** = any other native popup window of the browser.
- Internal pages share `si-*` components: toolbar buttons (`page.toolbar("Delete")`),
  snack bar (`page.wait_toast("deleted")`), `si-dialog`, right-click `si-action-menu`,
  left side bar with search + filters (`page.side_bar("Image")`).
- Pages, shortcuts and links that open "a page" open it in a NEW TAB:
  `web.switch_tab(url=cfg.page_url("history"))`.
- App menu button is "Samsung Browser"; its items carry the shortcut in the name
  ("Downloads Ctrl+J") - `native.menu("Downloads")` matches by prefix.

## Bookmarks (`internet://bookmarks`, prefix BM)

- Seed with `@pytest.mark.browser(bookmarks=...)`.
- Roots "PC bookmarks" > "Bookmark bar"; the tree is expanded. Rows have a round check box;
  Edit / Share / Delete / Select all are toolbar buttons acting on the selection ("Delete all" /
  "Deselect all" when everything is selected).
- Right click a row: Edit, Delete, Open all (n) in new tab / new window / Secret mode.
  Right ⋮: Add bookmark (`add_bookmark`, same dialog as Edit), Sort by name (folders first),
  Open all. Left ⋮: Create folder in selected folder, Sort by name, Import bookmarks (opens
  Settings in a new tab), Export bookmarks (Save As, HTML: `export(native, path)`).
- "Create folder" adds "Folder N" in the selected folder, opens it and edits its name in the
  tree (`add_folder(name)` types over it). Delete is immediate: snack bar "1 bookmark deleted"
  + Undo. Clicking a bookmark opens it in a NEW TAB.
- Import/Export use Windows file dialogs -> `native.file_dialog("open"/"save")`; import file:
  `files.bookmarks_html(...)`.
- Drag & drop inside the manager: `method="native"` (real mouse) is the reliable option;
  synthesized `html5` events are ignored there.
- Toolbar "Bookmarks" button -> panel: header buttons Add bookmark (adds the current page),
  Create folder, Expand (opens the manager); tree "PC bookmarks" > "Bookmark bar" (folders are
  Buttons `auto_id=folder`, bookmarks are TreeItems). Ui-map keys `bookmarks_panel_*`.
- Ctrl+D bookmarks at once: toast "Page bookmarked." [Edit] (`dialogs.bookmark_added`), no
  bubble; the star becomes "Remove from Bookmarks" (clicking it removes the bookmark, once
  the toast is gone - see "Whole product").
- The star (`PageActionView`) only shows when the omnibox has NO focus (focused, it shows
  other icons), and a page opened by `web.open` can leave the focus there: call
  `native.focus_page()` after opening the page and before Ctrl+D / any star check
  (BM-113, BM-114, BM-116). Old builds (31): class `StarView`, shown regardless of focus;
  the ui map matches both classes with `class_name_re`.
- Toast "Edit" -> edit bubble: Edits "Bookmark name" / "Bookmark URL" (URL shown without
  `http://`), "Create folder in selected folder", Save / Cancel. Toast text is "Page
  bookmarked." or "Bookmark added to <folder>" (page already bookmarked elsewhere).

## History (`internet://history`, prefix HIS)

- Seed by visiting `site.page(title)`; wait for the title before the next visit.
- Entries are newest first, grouped by day; `rows()` reads them in one call.
- Each row has a round check box (`select()`), the day header has its own (`#all-select`).
  Toolbar: Share, Delete (no confirmation), Clear history.
- Side bar time filters are CHECK BOXES (several ranges add up): `filter_time("Last hour")`
  leaves exactly the given ones ticked. "Clear browsing data" -> settings `clearBrowserData`
  in a new tab.
- Search is debounced; wait on the result (`web.wait_until(lambda: h.titles() == [...])`).
- Ctrl+H is a browser shortcut -> `native.hotkey("^h")`, opens a new tab.

## Downloads (`internet://downloads`, prefix DL)

- The session downloads into its own folder (`downloads_dir`); prompt is off by default.
  Turn on Save As with `browser(prefs={"download.prompt_for_download": True})` + native `file_dialog`.
- Side bar search + categories (All, Image, Video, Audio, Document, Others: `filter_category()`).
- Finished row: name, size ("2.05 KB"), source link, icons "Copy link", "Show in folder",
  X (remove, snack bar + Undo). In-progress row: progress bar + text buttons Pause/Resume,
  Cancel (`action(name, "Pause")`). Cancel REMOVES the row ("x removed from Downloads." + Undo);
  the toolbar Downloads bubble shows "Canceled". Toolbar: "Clear download history".
- A finished download opens the toolbar Downloads bubble over the page. Since build 155 it
  covers the downloads page toolbar button "Clear download history" (cases call it "Clear
  all"): close it first with
  `native.close_download_bubble()` (clicks its X, ui map `download_bubble_close`), then click
  (DL-003). Any test that downloads and then uses that toolbar needs this (+ `native`).
- "Show in folder"/"Open" launch Explorer / the default app (outside the browser): assert with
  `native.wait_explorer(...)` and close the window afterwards.
- Dangerous/blocked file types show a warning instead of finishing - pick safe types.

## Add-ons (`internet://extensions`, prefix ADD)

- Page title "Add-ons". Developer mode is a toggle in the LEFT side bar; on, the toolbar shows
  Load Unpacked, Pack add-on, Update and cards show the version. Card buttons Details / Remove
  (si-flat-button). Remove -> native bubble 'Delete <name>?' [Remove] [Cancel].
- Install prompt (store) -> 'Add "<name>"?' [Add] [Not now]; the store also shows
  Google's "Switch to Chrome?" bubble (ignore it). App menu has "Add-ons".
- Load with `browser(extensions=["sample_addon"])` (unpacked). `info()` returns state from
  `chrome.developerPrivate` (`ENABLED`/`DISABLED`).
- Prove an add-on is active through its effect on a page (content script attribute), not
  only through the toggle.
- Details: `open_details(name)` -> URL `?id=...`; read with `web.wait_page_text`.
- Install flows (all native):
  - Load unpacked: `pages.extensions.load_unpacked(native, folder)` (dev mode, button,
    Windows folder picker).
  - Web Store: `pages.webstore.install(ext_id, native)` - through the company proxy; button
    text from config `webstore.add_button_texts`; free, popular extensions only (Dark Reader
    in `resources/data/addons.yaml`).
- Toolbar "Add-ons" (puzzle, `ExtensionsToolbarButton`) -> menu: each add-on with "Pin <name>" /
  "Unpin <name>" and "More options for <name>" (menu: Options, Remove from Samsung Browser,
  Manage add-on, View web permissions). Pinned icon = `ToolbarActionView` named
  "<name>\nHas access to this site"; its popup is a Document readable through UIA.
- "Options" opens the add-on's options page in a BACKGROUND tab: WebDriver cannot read that
  chrome-extension:// tab (renderer timeout) - check `native.tab_titles()`, bring it to front
  by clicking its TabItem and read it with `native.wait_text(...)`.

## General browsing (prefix GEN)

- Tabs opened by the page: capture `before = web.tabs` first, then `web.wait_new_tab(before)`.
- `window.open` popups are windows; they also appear in `web.tabs`.
- `beforeunload` "Leave site?" is accepted automatically by chromedriver (WebDriver spec): the
  prompt can't be observed or dismissed; cases about it are not automatable with this stack.
