"""Reference: browser keyboard shortcuts (handled by the browser UI, so sent natively)."""
import pytest

pytestmark = pytest.mark.native


def test_ctrl_t_and_ctrl_w(web, native, site):
    web.open(site.page("Base tab"))
    before = web.tabs
    native.hotkey("^t")
    new = web.wait_new_tab(before)
    native.hotkey("^w")
    web.wait_until(lambda: new not in web.tabs, message="tab closed")
    web.switch_tab(title="Base tab")


@pytest.mark.parametrize("keys,page", [("^h", "history"), ("^j", "downloads")])
def test_shortcut_opens_internal_page(web, native, cfg, keys, page):
    before = web.tabs
    native.hotkey(keys)
    web.wait_new_tab(before)
    web.wait_url(cfg.page_url(page))


def test_ctrl_l_focuses_address_bar(web, native, site):
    web.open(site.page("Start"))
    native.hotkey("^l")
    native.type_text(site.page("Typed"))
    native.hotkey("{ENTER}", focus=False)
    web.wait_title("Typed")


def test_ctrl_d_bookmark_bubble_rename(web, native, site, pages):
    web.open(site.page("To bookmark"))
    native.hotkey("^d")
    bubble = native.wait_dialog("bookmark_added")
    bubble.set_text("Renamed in bubble")          # first Edit = name
    bubble.click("Done")
    pages.bookmarks.open().wait_item("Renamed in bubble")
