# Page objects

```
sbtest/pages/base.py        BasePage - helpers shared by every internal page
sbtest/pages/chromium/      upstream Chrome/Chromium implementation (verified, the reference)
sbtest/pages/samsung/       Samsung implementation: class X(chromium.X) + overrides
sbtest/pages/webstore.py    Chrome Web Store (public site, same for both targets)
```

Tests only use the `pages` fixture (`pages.extensions`, ...). It instantiates the class of
the current target (config `page_objects`: `samsung` or `chromium`). Page objects hold
selectors and page steps, **no assertions**: they return data and wait for their own effect.

## Adapting a Samsung page (the common job)

1. Dump both: `python -m sbtest.tools.dom extensions --interactive --out sam.txt` and
   `python -m sbtest.tools.dom extensions --interactive --target chrome --out chr.txt`.
2. In `sbtest/pages/samsung/<page>.py` override only what differs: class constants
   (`ROOT`, `ITEMS`, `DEV_MODE` ...) first, then methods whose flow differs (e.g. a
   confirmation that is a cr-dialog in Samsung but native in Chrome).
3. Keep method names, parameters and return types of the parent - tests in
   `tests/features/` must not change per target.
4. Update the module docstring STATUS line: `VERIFIED on Samsung <version> (<date>)` and list
   what differs.
5. Run the feature on both targets: `python run.py --feature extensions` and
   `python run.py --target chrome --feature addons`.

Private APIs: `ExtensionsPage.info()` (`chrome.developerPrivate`) and `SettingsPage.get_pref()`
(`chrome.settingsPrivate`) exist on upstream pages; a rewritten Samsung page may not expose
them - check `web.js("return typeof chrome.developerPrivate")` and override with a UI-based read.

Rewritten pages built with React/Vue/plain DOM: `>>>` is only needed where a shadow root
exists; `text=`, `aria=`, `deepcss=` work everywhere. Prefer `id`, `data-*`, `aria-*`;
never generated class names (`css-1x2y3z`).

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

## Existing page APIs (same names on both targets)

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
- `settings`: `open_section(name)`, `menu(label)`, `toggle/is_on/set_toggle(label)`,
  `radio/choose_radio`, `dropdown/choose(label, option)`, `get_pref`, `set_pref`

## Adding a new page

1. Path key in `config/default.yaml` -> `pages:` (scheme comes from the target).
2. `sbtest/pages/chromium/<name>.py` (when the page exists upstream) and
   `sbtest/pages/samsung/<name>.py`; export the class in both packages' `__init__`.
3. Register the class name in `PAGE_CLASSES` (`sbtest/pages/__init__.py`).
4. Reading lists: one JS call over the rows (see `HistoryPage.rows`, `DownloadsPage.info`) -
   lists re-render and per-row calls go stale.
