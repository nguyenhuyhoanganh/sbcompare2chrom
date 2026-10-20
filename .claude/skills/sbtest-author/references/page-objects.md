# Page objects

One class per internal page in `sbtest/pages/`. They hold selectors (class constants)
and page-specific steps. **No assertions** in page objects - return data, let tests assert.

```python
class BookmarksPage(BasePage):
    page = "bookmarks"                     # key of config `pages` -> URL (scheme can differ in the fork)
    ROOT = "bookmarks-app >>> bookmarks-list"   # proves the page rendered (wait_loaded)
    ITEMS = "bookmarks-app >>> bookmarks-list >>> bookmarks-item"

    def titles(self) -> list[str]: ...     # read
    def add_bookmark(self, name, url): ... # act + wait for the result, no assert
```

## BasePage gives you (all Chromium WebUI pages share these widgets)

| method | for |
|--------|-----|
| `open(subpath="")` / `wait_loaded()` / `is_open()` / `url` | navigation |
| `search(text)` / `clear_search()` | `cr-toolbar-search-field` (override `SEARCH_INPUT` if needed) |
| `find_by_text(css, text, contains=False, within=None)` | visible element of `css` with that text, any shadow depth |
| `click_text(text, css=..., within=None)` | click buttons/links/menu items by label |
| `click_menu_item(text)` | item of the open `cr-action-menu` |
| `wait_toast(contains="")` / `toast_action("Undo")` / `toast_element()` | `cr-toast` |
| `open_dialog()` / `dialog_text()` / `dialog_input(id)` / `dialog_button(text)` / `wait_dialog_closed()` | `cr-dialog` |
| `q(value)` | quote a value for CSS attribute selectors: `f"[aria-label={q(name)}]"` |

## Existing page objects (upstream Chromium reference - adapt to Samsung)

- `pages.bookmarks`: `titles, item, has_item, wait_titles, wait_item, folders, expand_tree,
  open_folder, open_item, organize(action), add_bookmark, add_folder, item_menu(title, action),
  edit, delete -> toast text, select(*titles), delete_selected, undo, save_dialog`
- `pages.history`: `rows -> [{title,url,domain,time}], titles, urls, item, has_item, wait_item,
  is_empty, open_item, select, delete_selected(confirm), item_menu, remove, open_clear_browsing_data`
- `pages.downloads`: `items, info(item) -> {name,url,description,tag,in_progress}, names, item,
  wait_item, wait_complete, status, action(name, "Pause"|"Resume"|"Cancel"|"Show in folder"...), remove, clear_all`
- `pages.settings`: `open_section(name), menu(label), toggle/is_on/set_toggle(label), radio/choose_radio,
  dropdown/choose(label, option), get_pref(name), set_pref(name, value)`
- `pages.extensions`: `info() -> [{id,name,version,state,...}], names, item, ext_id, is_enabled,
  set_enabled, set_dev_mode, open_details, click_remove, wait_installed, wait_gone,
  load_unpacked(native, dir), drop_crx(native, crx)`
- `pages.webstore`: `open_item(id), is_installed, install(id, native)` (text based, store site)

Note `info()` / `get_pref()` call private Chromium APIs (`chrome.developerPrivate`,
`chrome.settingsPrivate`) that the rewritten Samsung pages may not expose; check with
`web.js("return typeof chrome.developerPrivate")` and fall back to reading the UI.

Pages built with React/Vue/plain DOM instead of Polymer/Lit: the same locators work
(`>>>` is only needed where a shadow root exists; `text=`, `aria=`, `deepcss=` work
everywhere). Prefer `data-*`/`id`/`aria-*` attributes; generated class names
(`css-1x2y3z`, `_a1b2`) change every build - never use them.

## Adding a page object

1. Explore: `python -m sbtest.tools.dom <url> --interactive` (and without `--interactive` for structure).
2. Create `sbtest/pages/<name>.py`, subclass `BasePage`, set `page` and `ROOT`.
3. Add the URL key to `config/default.yaml` -> `pages:` if it is a new internal page.
4. Register in `sbtest/pages/__init__.py` -> `Pages.REGISTRY` and `__all__`.
5. Prefer stable hooks: element ids, custom element tags, `aria-label`, visible text.
   Avoid `:nth-of-type` and CSS classes used for styling.
6. Reading lists: do it in **one JS call** over the rows (see `HistoryPage.rows`,
   `DownloadsPage.info`) - lists re-render and per-row Selenium calls go stale.
7. Every action method waits for its own effect (e.g. `add_folder` waits for the item)
   so tests stay short.

## Extending for Samsung-specific UI

When the fork adds or renames controls, change the selector constants / text labels in
the page object, not the tests. If Samsung and upstream differ and you need both (e.g.
running the suite on plain Chromium as a reference), branch on `self.web.cfg.get(...)`
with a config flag rather than try/except guessing.
