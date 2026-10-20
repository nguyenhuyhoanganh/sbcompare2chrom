# Native layer (`native`) - pywinauto, UIA backend, Windows only

Use it for everything outside web content. Mark the test `@pytest.mark.native`; the
`native` fixture skips the test automatically where it cannot work (Linux, headless,
pywinauto missing).

## Discover before you write

```
python -m sbtest.tools.uia_dump --out artifacts/uia_main.txt                      # whole frame
python -m sbtest.tools.uia_dump --url /pages/page1.html --keys "^d" --find "(?i)bookmark|done"
python -m sbtest.tools.uia_dump --pid <pid>          # attach to a browser you opened by hand
python -m sbtest.tools.dom bookmarks --uia artifacts/uia.txt   # DOM + UIA in one go
```

Lines look like `Button 'Done' auto_id='' class='MdTextButton' rect=(..)`. Put stable
criteria into `config/native_ui.yaml` (logical name -> criteria) and use the name:

```yaml
bookmark_star:
  control_type: Button
  title_re: "(?i)bookmark this tab|add to bookmarks"
dialogs:
  bookmark_added: "(?i)bookmark added|edit bookmark"
```

Criteria keys: `title`, `title_re`, `control_type`, `auto_id`, `class_name`, `found_index`.
Prefer `control_type` + `title_re` (case-insensitive) over `found_index`. Samsung's UI
strings can differ from Chromium's - always verify on the real build; locale of the
browser is forced to en-US by `--lang=en-US` in config.

## API

```python
native.hotkey("^d")            # browser shortcut (focuses the frame first). ^ Ctrl, + Shift, % Alt
native.hotkey("^+{DELETE}")    # Ctrl+Shift+Del ; {ENTER} {ESC} {TAB} {F5} {DOWN}
native.type_text("literal text")
native.click("bookmark_star")  # logical name from native_ui.yaml, or a criteria dict
native.element("omnibox") / native.exists("downloads_button")
native.navigate(url)           # Ctrl+L, type, Enter - like a user in the address bar
native.omnibox_text()
native.tab_titles()
native.menu("Bookmarks", "Bookmark manager")   # app menu path (regex prefix per item)
native.select_menu_items("Open link in new tab")   # in an already open native menu
native.menu_items()            # names in the open menu(s)
native.context_menu_web(web, "#link", "Open link in new tab")   # real right click on DOM element

dlg = native.wait_dialog("bookmark_added")     # logical name (native_ui.yaml dialogs) or regex
dlg.texts() / dlg.text() / dlg.title
dlg.click("Done") / dlg.set_checkbox("Show bookmarks bar", True) / dlg.set_text("x", auto_id="..")
dlg.press("{ESC}") / dlg.close() / dlg.wait_closed() / dlg.dump()

fd = native.file_dialog("save")   # Windows common dialog opened by the browser
fd.save_as(tmp_path / "page.html")  # handles "replace?" confirmation
fd = native.file_dialog("open"); fd.open(file) / fd.open(f1, f2) / fd.cancel()
fd.select_folder(folder)            # "Load unpacked", "Change download location"

native.wait_text(r"(?i)bookmark added")   # any element name in any browser window
native.has_text(r"(?i)downloading")
native.wait_os_toast(r"(?i)sbtest notification")

native.click_web_element(web, loc)        # real mouse click on a DOM element
native.drag_web_element(web, src, dst)    # real mouse drag inside the page
native.drag_web_to_ui(web, "#link", "bookmarks_bar")
native.drag((x1, y1), (x2, y2))
native.screenshot(path) / native.dump(path) / native.close_stray_dialogs()
```

## Patterns

**Bubble after a shortcut**
```python
native.hotkey("^d")
bubble = native.wait_dialog("bookmark_added")
assert "Static page 1" in bubble.texts()      # name field value is included (Edit values)
bubble.click("Done"); bubble.wait_closed()
```

**Download with "Ask where to save" on**
```python
@pytest.mark.browser(prefs={"download.prompt_for_download": True})
...
web.click("#dl-txt")
native.file_dialog("save").save_as(downloads_dir / "renamed.txt")
web.wait_file(downloads_dir, "renamed.txt")
```

**Native action that opens a tab** -> sync Selenium:
```python
before = web.tabs; native.hotkey("^h"); web.wait_new_tab(before)
```

**Native confirmation from a WebUI page** (e.g. Remove extension):
```python
pages.extensions.click_remove(name)
native.wait_dialog("remove_extension").click("Remove")
pages.extensions.wait_gone(name)
```

## Traps

- Native input needs the browser window in the foreground on an unlocked desktop.
  Do not run native tests over RDP minimized / with screen locked; use a real or VM session.
- Keep windows unique: the framework identifies windows by the browser PID; don't
  run a manual Samsung Internet instance with the same profile.
- `invoke()` vs real click: `Dialog.click` tries UIA invoke, then a real click. For Views
  buttons that ignore invoke use `real_mouse=True`.
- DPI scaling: coordinates from `web_point` already multiply by `devicePixelRatio`.
- Menus are separate top-level windows of the browser process; `select_menu_items`
  searches all of them.
- If a dialog is not found, dump: `native.dump("artifacts/uia_now.txt")` right before the wait.
