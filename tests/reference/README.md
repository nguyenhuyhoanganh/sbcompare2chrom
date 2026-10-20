# Interaction reference suite

Working examples of every kind of interaction the framework supports, meant to run on
**Chrome** (`python run.py --target chrome --suite reference`). Samsung Internet shares the
Chromium base, so when a Samsung test needs an interaction, copy the pattern from here.
The tests use only the local test site (`test_site/`), never internet.

| Need | Example |
|------|---------|
| open / back / forward / refresh, redirects, error pages | `web/test_navigation_tabs.py` |
| new tab from link, `window.open` popup, switch / close tabs | `web/test_navigation_tabs.py` |
| text, number, date, range, multi-select, contenteditable | `web/test_inputs_keyboard.py` |
| keys and chords inside a page (Enter, Ctrl+A, Shift+Tab) | `web/test_inputs_keyboard.py` |
| full form with checkbox, radio, select, file, submit | `web/test_inputs_keyboard.py` |
| click, double click, page context menu, hover menu, scrolling | `web/test_mouse.py` |
| drag & drop (HTML5, sortable list, mouse drag) | `web/test_drag_and_drop.py`, `web/test_mouse.py` |
| alert / confirm / prompt / `<dialog>` (and why "Leave site?" can't be tested) | `web/test_js_dialogs.py` |
| read text, lists, attributes, state; wait for late content, in-page toast | `web/test_reading_and_waits.py` |
| Shadow DOM locators, iframes | `web/test_shadow_dom_and_frames.py` |
| upload via `<input type=file>`, downloads to the profile folder | `web/test_upload_download_web.py` |
| upload through the Windows **Open** dialog (single, multiple, cancel) | `files/test_upload_os_dialog.py` |
| download through **Save As** (rename, other folder, cancel) | `files/test_downloads_save_as.py` |
| Save page (Ctrl+S, context menu "Save as") | `files/test_save_page.py` |
| Windows **folder picker** | `files/test_folder_picker.py` |
| drag a file **from File Explorer** onto a page; "Show in folder" opens Explorer | `files/test_file_explorer.py` |
| address bar, back/forward/reload buttons, new tab button, tab strip, app menu, star | `native/test_browser_ui.py` |
| browser shortcuts (Ctrl+T/W/L/H/J/D) | `native/test_shortcuts.py` |
| native context menu on a link / page | `native/test_context_menus.py` |
| HTTP sign-in dialog, notification / location permission prompts | `native/test_browser_prompts.py` |
| print preview dialog | `native/test_print_dialog.py` |
| Windows toast notification | `native/test_os_notifications.py` |

Add-on install prompts (Load unpacked, drop .crx, Web Store, remove confirmation) are in the
product tests: `tests/features/addons/`.

`web/` runs anywhere (also headless). `files/` and `native/` need Windows with an unlocked
desktop; they are skipped elsewhere.
