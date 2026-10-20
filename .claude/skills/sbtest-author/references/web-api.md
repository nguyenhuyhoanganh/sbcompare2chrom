# Web layer API (`web`)

Every method takes a **locator string** or a WebElement. Every finder waits (default
`timeouts.default` = 10 s) for a *visible* element unless said otherwise.

## Locators

| Syntax | Meaning |
|--------|---------|
| `"#id .cls"` / `"css=..."` | CSS in the light DOM of the document |
| `"xpath=//a"` or `"//a"` | XPath (light DOM only) |
| `"id=x"`, `"name=q"` | attribute shortcuts |
| `"a-app >>> #toolbar >>> input"` | **shadow path**: each `>>>` searches inside the `shadowRoot` of what matched before |
| `"deepcss=cr-toast"` | CSS searched in **every** shadow root (handy, slower, may match several) |
| `"text=Delete"` | deepest visible element whose composed text is exactly `Delete` (pierces shadow) |
| `"text~=deleted"` | text contains, case-insensitive |
| `"aria=Search bookmarks"` | `aria-label` / `title` / `placeholder` / `label` equals (pierces shadow) |
| `(By.CSS_SELECTOR, "x")` | Selenium tuple also accepted |

Scoping: `web.find("deep=#menuButton", within=row)` searches **inside row's shadowRoot**
(`deep=` with one segment). CSS/XPath with `within=` search row's light DOM.
`text=`/`aria=`/`deepcss=` with `within=` search the row's subtree incl. its shadow.

Get locators from the explorer instead of writing them by hand:

```
python -m sbtest.tools.dom bookmarks --interactive
python -m sbtest.tools.dom history --exec "web.open(site.page('A'))" --exec "web.open('chrome://history')"
python -m sbtest.tools.dom /form.html --out artifacts/form.txt
```

Each output line ends with `=>  <locator>`. Prefer ids (`#saveButton`) and stable tags
(`bookmarks-item`) over `:nth-of-type`. If a locator needs `:nth-of-type`, prefer a text
or aria based lookup (`find_by_text`, `aria=`).

## Waits (never sleep)

```python
web.find(loc, timeout=None, visible=True, within=None)  # -> element
web.find_all(loc, visible=True, within=None)            # no wait, may be []
web.wait_visible(loc) / web.wait_present(loc) / web.wait_gone(loc)
web.wait_count(loc, 3)
web.wait_text(loc, "Saved", contains=True)
web.wait_page_text("Saved")            # anywhere on the page incl. shadow DOM
web.wait_url("/echo") / web.wait_title("Static page 2") / web.wait_ready()
web.wait_until(lambda: pages.bookmarks.titles() == ["A", "B"], message="A,B listed")
web.wait_file(downloads_dir, "*.pdf", timeout=web.long_timeout)
```

## Actions

```python
web.click(loc)                 # scrolls into view, retries stale/intercepted, JS-click fallback
web.js_click(loc)              # force (hidden or covered elements)
web.double_click(loc) / web.right_click(loc) / web.hover(loc)
web.type(loc, "text", clear=True, enter=False)
web.clear(loc) / web.set_value(loc, "v")      # set_value: JS + input/change events
web.press("ENTER") / web.press(Keys.CONTROL, "a") / web.press("TAB", loc="#name")
web.select("#color", text="Blue")  # native <select> (also value=/index=)
web.set_checked(loc, True)         # checkbox, cr-checkbox, cr-toggle, radio
web.drag_and_drop(src, dst, method="actions"|"html5"|"native")
web.drag_by(loc, dx, dy)
web.upload("#file", path1, path2)  # input[type=file], no OS dialog
web.scroll_to(loc) / web.scroll_by(0, 600)
```

Typing into Chromium `cr-input`: target the inner input: `"... >>> cr-input#name >>> input"`
or page-object helpers (`page.dialog_input("name")`).

Drag & drop choice: `html5` for `draggable=true` + dataTransfer pages; `actions` for
mouse-event based widgets/sortables; `native` (real mouse, Windows) for anything that
must cross into browser UI or when the other two do not trigger the app's handlers.

## Reading

```python
web.text(loc)          # composed text (includes the element's shadow content)
web.texts(loc)         # list for all visible matches
web.page_text()        # everything visible on the page, shadow DOM included
web.attr(loc, "href") / web.prop(loc, "checked") / web.value(loc)
web.exists(loc) / web.is_visible(loc) / web.count(loc) / web.is_enabled(loc) / web.is_checked(loc)
web.table("table#t")   # [{header: cell}]
web.focused()          # deepest active element
web.url / web.title / web.tabs
```

## Tabs, windows, JS dialogs, misc

```python
before = web.tabs; web.click("#blank-link"); web.wait_new_tab(before)   # switches to it
web.switch_tab(index=0) / web.switch_tab(title="History") / web.switch_tab(url="settings")
web.new_tab(url) / web.close_tab()
web.accept_alert() -> text / web.accept_alert(prompt_text="x") / web.dismiss_alert() / web.has_alert()
web.js("return document.title") / web.cdp("Browser.getVersion") / web.screenshot(path)
web.open(url) / web.open_internal("history") / web.back() / web.forward() / web.refresh()
```

Browser-owned dialogs that are **not** JS dialogs (bubbles, permission prompts, Save As,
print preview, "Add extension?") are native: see native-ui.md.
