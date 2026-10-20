# Test data and preconditions

Rule: preconditions are created **before** the browser starts (profile seeding) or with
the cheapest reliable action (visiting a local page). Only the behaviour under test goes
through the UI. Everything is local - no internet.

## Per-test browser preconditions: `@pytest.mark.browser(...)`

```python
@pytest.mark.browser(bookmarks="seed_basic")                 # key in test_data/<feature>.yaml
@pytest.mark.browser(bookmarks="bookmarks:seed_many")        # explicit file:key
@pytest.mark.browser(bookmarks={"bookmark_bar": [{"name": "A", "url": "{site}/page?title=A"}]})
@pytest.mark.browser(prefs={"download.prompt_for_download": True, "bookmark_bar.show_on_all_tabs": True})
@pytest.mark.browser(extensions=["sample_addon"])             # test_data/extensions/<dir>, unpacked
@pytest.mark.browser(args=["--start-maximized"])              # extra switches
@pytest.mark.browser(profile="with_passwords")                # copy test_data/profiles/<name>/ first
```

A test with `browser(...)` always gets its own fresh browser, even when the run reuses
browsers (`--browser-scope session`).

## Data files: `test_data/<feature>.yaml`

```yaml
seed_basic:                     # Bookmarks file structure
  bookmark_bar:
    - {name: Static page 1, url: "{site}/pages/page1.html"}
    - name: Work
      children:
        - {name: Form page, url: "{site}/form.html"}
  other:
    - {name: Other page, url: "{site}/pages/page3.html"}
new_bookmark: {name: My new bookmark, url: "{site}/page?title=New"}
```

`{site}` becomes the local server base URL. In a test: `d = data("bookmarks"); d["new_bookmark"]["url"]`.
Roots: `bookmark_bar`, `other`, `synced`.

In code: `BookmarksSeed().url("A", url).folder("F", [Bm("B", url2), Folder("Empty")])` and
`session.profile.bookmarks(seed)` before `session.start()` (only when building a session by hand).

## Local site (`site` fixture)

| URL | Use |
|-----|-----|
| `site.page("Alpha")` | page whose `<title>` and `h1#title` are `Alpha` - unique history/bookmark entries |
| `site.url("/pages/page1.html")` | static pages 1..3 with `#next` links, `#body` paragraph |
| `site.url("/form.html")` | all form controls + file input, submits multipart to `/upload` |
| `site.url("/inputs.html")` | text/number/date/range/multi-select/contenteditable/disabled, key log `#last-key` |
| `site.url("/mouse.html")` | click, double click, page context menu, hover menu, far element |
| `site.url("/upload.html")` | `#file` input, `#pick` button -> OS Open dialog (`#picked`), `#drop-zone` for Explorer drags (`#dropped`) |
| `site.url("/dialogs.html")` | alert / confirm / prompt / beforeunload / print (async) / `<dialog>` |
| `site.url("/dragdrop.html")` | HTML5 DnD, sortable list, mouse drag box |
| `site.url("/popups.html")` | target=_blank link, window.open, same-tab link |
| `site.url("/downloads.html")` | `#dl-txt` 2 KB, `#dl-bin` 100 KB, `#dl-slow` 10 MB slow, `#dl-attr` download attribute |
| `site.url("/frames.html")` | iframe `#inner` with input/button posting to the parent |
| `site.url("/permissions.html")` | notification and location permission requests |
| `site.url("/toast.html")` | in-page toast |
| `site.url("/shadow.html")` | nested custom elements (locator practice) |
| `site.download("a.pdf", 4096, "application/pdf")` | any attachment |
| `site.slow_download("big.bin", size, chunk, delay)` | in-progress downloads (pause/cancel) |
| `site.url("/redirect", to="/page?title=X")` / `site.url("/status", code=404)` | redirects / error pages |
| `site.url("/basic-auth")` | HTTP sign-in prompt, user `sbtest` / password `sbtest` |
| `site.url("/delayed", ms=1500, text="Ready")` | `#late` appears after a delay |
| `/echo` (GET/POST form) , `/upload` (POST multipart) | server echoes what it received as JSON |

Need a new page? Add an HTML file under `test_site/` (static) or a route in
`sbtest/server/local_site.py` (dynamic), with ids on everything the tests touch.

## History

There is no history seeding file: visit pages. `web.open(site.page(t)); web.wait_title(t)`.

## Files

```python
from sbtest.data import files
files.text_file(tmp_path, "a.txt", "content")
files.binary_file(tmp_path, "a.bin", 4096)
files.png_file(tmp_path, "img.png")
files.bookmarks_html(tmp_path, [("Title", url)])   # Netscape file for "Import bookmarks"
```

## Unique values

`from sbtest.utils import unique` -> `unique("Folder")` = `Folder_1a2b3c`. Use for every
name a test creates so reruns and shared browsers never collide.

## Settings state

Fresh profile = default settings + `browser.prefs` from config. For a non-default start
state use `browser(prefs=...)`. To verify, use `pages.settings.get_pref(name)` (on a
settings page). Pref names: open `chrome://prefs-internals` in the browser.

## Add-ons

`test_data/addons.yaml`: `sample` (name, unpacked folder, `.crx`) and `webstore` (id, name).
Put unpacked add-ons in `test_data/extensions/<name>/` (manifest v3); pack a `.crx` with
`chrome.exe --pack-extension=<folder>` (Chrome for Testing from `browsers/chrome/` works). `sample_addon` has a
popup, an options page and a content script that sets `<html data-sb-addon="active">` on
`http://127.0.0.1/*`. Installing from a store needs internet - not used in automated tests;
test the install *flow* with a local `.crx` only if the build allows it.
