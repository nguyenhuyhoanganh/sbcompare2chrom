# Page objects

```
sbtest/pages/base.py        BasePage - helpers for Samsung's si-* components, shared by every page
sbtest/pages/bookmarks.py   history.py   downloads.py   extensions.py   (internal pages)
sbtest/pages/webstore.py    Chrome Web Store item page (public site)
```

Tests only use the `pages` fixture (`pages.extensions`, ...). Page objects hold selectors and
page steps, **no assertions**: they return data and wait for their own effect. Each module
docstring has a STATUS line (the Samsung version it was verified on) and how the page differs
from upstream Chromium.

## When a page changed (after a Samsung/Chromium update)

1. Dump it: `python -m sbtest.tools.dom extensions --interactive --out ext.txt`
   (with data: `--seed-bookmarks ...`, `--extension resources/extensions/sample_addon`).
2. Fix class constants (`ROOT`, `ITEMS`, `DEV_MODE` ...) first, then methods whose flow
   changed (e.g. a confirmation that became a native prompt instead of a si-dialog).
3. Keep method names, parameters and return types - tests must not change.
4. Update the STATUS line: `verified on Samsung Browser <version> (<date>)`.
5. Run the feature: `python run.py --feature addons`.

Private APIs: `ExtensionsPage.info()` uses `chrome.developerPrivate` (works on Samsung 31);
if a build stops exposing it, check `web.js("return typeof chrome.developerPrivate")` and
switch to a UI-based read.

`>>>` is only needed where a shadow root exists; `text=`, `aria=`, `deepcss=` work everywhere.
Prefer `id`, `data-*`, `aria-*`; never generated class names (`css-1x2y3z`).

## BasePage helpers

| method | for |
|--------|-----|
| `open(subpath="")` / `wait_loaded()` / `is_open()` / `url` | navigation (URL from config `pages`) |
| `search(text)` / `clear_search()` | toolbar search field (`SEARCH_INPUT`) |
| `find_by_text(css, text, contains=False, within=None)` | visible element of `css` with that text, any shadow depth |
| `click_text(text, css=..., within=None)` | buttons/links/menu items by label |
| `click_menu_item(text)` | item of the open action menu |
| `wait_toast(contains="")` / `toast_action("Undo")` | toast |
| `open_dialog()` / `dialog_text()` / `dialog_input(id)` / `dialog_button(text)` / `wait_dialog_closed()` | in-page dialog |
| `q(value)` | quote for CSS attribute selectors: `f"[aria-label={q(name)}]"` |

## Existing page APIs

- `extensions`: `info() -> [{id,name,version,state,...}]`, `names`, `item`, `ext_id`, `is_enabled`,
  `set_enabled`, `set_dev_mode`, `open_details`, `click_remove`, `wait_installed`, `wait_gone`,
  `load_unpacked(native, dir)`, `drop_crx(native, crx)`
- `webstore`: `open_item(id)`, `is_installed`, `install(id, native)`
- `bookmarks`: `titles`, `item`, `has_item`, `wait_titles`, `wait_item`, `folders`, `expand_tree`,
  `open_folder`, `open_item`, `organize(action)`, `add_bookmark`, `add_folder`,
  `item_menu(title, action)`, `edit`, `delete -> toast`, `select(*titles)`, `delete_selected`, `undo`
- `history`: `rows -> [{title,url,domain,time}]`, `titles`, `urls`, `item`, `has_item`, `wait_item`,
  `is_empty`, `open_item`, `select`, `delete_selected(confirm)`, `item_menu`, `remove`,
  `open_clear_browsing_data`
- `downloads`: `items`, `info(item) -> {name,url,description,tag,in_progress}`, `names`, `item`,
  `wait_item`, `wait_complete`, `status`, `action(name, "Pause"|"Resume"|"Cancel"|"Show in folder"...)`,
  `remove`, `clear_all`

## Adding a new page

1. Path key in `config/default.yaml` -> `pages:` (navigation uses `chrome://<path>`, the
   address bar shows `internet://<path>`).
2. `sbtest/pages/<name>.py`: `class XPage(BasePage)` with `page`, `ROOT` and the page's steps.
3. Register it in `PAGE_CLASSES` and `__all__` (`sbtest/pages/__init__.py`).
4. Reading lists: one JS call over the rows (see `HistoryPage.rows`, `DownloadsPage.info`) -
   lists re-render and per-row calls go stale.
