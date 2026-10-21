"""Add-ons from the browser toolbar (app menu, Add-ons menu, pinned icon, popup) on Samsung Browser.
Cases: testcases/addons/toolbar.md. Windows only (native UI).

The popup belongs to the sample add-on (test_data/extensions/sample_addon/popup.html):
title "SB Sample Addon" and a button #count "Clicked N" that counts clicks.
"""
import pytest

from sbtest.steps import step

ADDON = "SB Sample Addon"
POPUP_COUNTER = {"control_type": "Button", "auto_id": "count"}   # content of the sample add-on popup

pytestmark = pytest.mark.native
uses_addon = pytest.mark.browser(extensions=["sample_addon"])


def pin(native, name=ADDON):
    native.click("extensions_button")
    native.click("addons_menu_pin", name=name)
    native.hotkey("{ESC}", focus=False)
    native.element("extension_action", name=name)


@pytest.mark.case("ADD-106")
def test_open_from_app_menu(web, native, cfg):
    with step("1. App menu > Add-ons", expected="Add-ons page"):
        native.menu("Add-ons")
        web.switch_tab(url=cfg.page_url("extensions"))


@uses_addon
@pytest.mark.sanity
@pytest.mark.case("ADD-111")
def test_pin_from_addons_menu(web, native, site):
    web.open(site.url("/index.html"))
    with step("1. Toolbar Add-ons", expected="menu lists the add-on with Pin and More options"):
        native.click("extensions_button")
        native.element("addons_menu_pin", name=ADDON)
        native.element("addons_menu_more", name=ADDON)
    with step("2. Pin", expected="the add-on icon appears in the toolbar"):
        native.click("addons_menu_pin", name=ADDON)
        native.hotkey("{ESC}", focus=False)
        native.element("extension_action", name=ADDON)
    with step("3. Add-ons menu > Unpin", expected="the icon leaves the toolbar"):
        native.click("extensions_button")
        native.click("addons_menu_unpin", name=ADDON)
        native.hotkey("{ESC}", focus=False)
        web.wait_until(lambda: not native.exists("extension_action", name=ADDON), message="icon unpinned")


@uses_addon
@pytest.mark.sanity
@pytest.mark.case("ADD-112")
def test_popup_from_toolbar_icon(web, native, site):
    web.open(site.url("/index.html"))
    pin(native)
    with step("1. Click the add-on icon", expected="popup 'SB Sample Addon' with 'Clicked 0'"):
        native.click("extension_action", name=ADDON)
        counter = native.element(POPUP_COUNTER, in_main=False)
        assert counter.element_info.name == "Clicked 0"
    with step("2. Click the popup button", expected="'Clicked 1' - the popup page runs"):
        counter.click_input()
        web.wait_until(lambda: native.element(POPUP_COUNTER, in_main=False).element_info.name == "Clicked 1",
                       message="popup counter incremented")


@uses_addon
@pytest.mark.case("ADD-113")
def test_more_options_opens_options_page(web, native, site):
    web.open(site.url("/index.html"))
    with step("1. Add-ons menu > More options", expected="Options, Remove from Samsung Browser, Manage add-on"):
        native.click("extensions_button")
        native.click("addons_menu_more", name=ADDON)
        items = native.menu_items()
        for item in ("Options", "Remove from Samsung Browser", "Manage add-on"):
            assert item in items, items
    with step("2. Options", expected="the add-on options page opens in a new tab"):
        native.select_menu_items("Options")
        # WebDriver does not answer for this chrome-extension:// tab (renderer timeout), so the
        # check goes through UIA: tab strip, then the page text once the tab is in front
        web.wait_until(lambda: "SB options" in native.tab_titles(), message="'SB options' tab")
        native.click({"control_type": "TabItem", "title": "SB options"})
        native.wait_text("^SB Sample Addon options$")
