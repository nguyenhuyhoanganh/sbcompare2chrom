"""Reference: the browser's own UI - address bar, toolbar buttons, tab strip, app menu, star."""
import pytest

from sbtest.steps import step

pytestmark = pytest.mark.native


def test_address_bar_navigate_and_read(web, native, site):
    url = site.url("/pages/page2.html")
    native.navigate(url)                          # Ctrl+L, type, Enter
    web.wait_title("Static page 2")
    assert "page2.html" in native.omnibox_text()


def test_back_forward_reload_buttons(web, native, site):
    web.open(site.url("/pages/page1.html"))
    web.click("#next")
    web.wait_title("Static page 2")
    native.click("back_button")
    web.wait_title("Static page 1")
    native.click("forward_button")
    web.wait_title("Static page 2")
    web.js("window.__marker = 1")
    native.click("reload_button")
    web.wait_until(lambda: web.js("return window.__marker === undefined"), message="page reloaded")


def test_new_tab_button_and_tab_titles(web, native, site):
    web.open(site.page("First tab"))
    before = web.tabs
    native.click("new_tab_button")
    web.wait_new_tab(before)
    web.open(site.page("Second tab"))
    web.wait_until(lambda: all(any(t in title for title in native.tab_titles()) for t in ("First tab", "Second tab")),
                   message="both tabs in the tab strip")


def test_app_menu_opens_history(web, native, cfg):
    before = web.tabs
    with step("App menu > History > History", expected="History page in a new tab"):
        native.menu("History", "History")
        web.wait_new_tab(before)
        web.wait_url(cfg.page_url("history"))


def test_bookmark_star_bubble(web, native, site, pages):
    web.open(site.page("Starred page"))
    native.click("bookmark_star")
    bubble = native.wait_dialog("bookmark_added")
    assert "Starred page" in bubble.texts()       # name field value
    bubble.click("Done")
    bubble.wait_closed()
    pages.bookmarks.open().wait_item("Starred page")
