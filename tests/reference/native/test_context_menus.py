"""Reference: native (browser) context menus on page content."""
import pytest

pytestmark = pytest.mark.native


def test_link_open_in_new_tab(web, native, site):
    web.open(site.url("/popups.html"))
    before = web.tabs
    native.context_menu_web(web, "#same-link", "Open link in new tab")
    web.wait_new_tab(before, switch=False)


def test_read_and_dismiss_page_menu(web, native, site):
    web.open(site.url("/pages/page1.html"))
    native.context_menu_web(web, "#body")         # open only
    items = native.menu_items()
    assert any(i.lower().startswith("back") for i in items), items
    native.hotkey("{ESC}", focus=False)
