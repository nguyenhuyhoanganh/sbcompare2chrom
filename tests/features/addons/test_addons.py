"""Add-ons (extensions). Cases: cases/addons/addons.md

The sample add-on (resources/extensions/sample_addon) is loaded unpacked with
@pytest.mark.browser(extensions=[...]). Its content script sets
<html data-sb-addon="active"> on local pages, which proves it is running.
"""
import pytest

from sbtest.steps import step

ADDON = "SB Sample Addon"
uses_addon = pytest.mark.browser(extensions=["sample_addon"])


def page_marked(web, site) -> bool:
    web.open(site.url("/index.html"))
    return web.js("return document.documentElement.getAttribute('data-sb-addon')") == "active"


@uses_addon
@pytest.mark.sanity
@pytest.mark.case("ADD-001")
def test_addon_listed_and_active(pages, web, site):
    e = pages.extensions
    with step("1. Open extensions page", expected="add-on listed and enabled"):
        e.open()
        assert ADDON in e.names()
        assert e.is_enabled(ADDON)
    with step("2. Open a local page", expected="page marked by content script"):
        web.wait_until(lambda: page_marked(web, site), message="content script ran")


@uses_addon
@pytest.mark.case("ADD-002")
def test_disable_addon(pages, web, site):
    e = pages.extensions.open()
    with step("1. Turn the add-on off", expected="state DISABLED"):
        e.set_enabled(ADDON, False)
        web.wait_until(lambda: [x["state"] for x in e.info() if x["name"] == ADDON] == ["DISABLED"],
                       message="state DISABLED")
    with step("2. Open a local page", expected="not marked"):
        assert not page_marked(web, site)


@uses_addon
@pytest.mark.case("ADD-003")
def test_details_page(pages, web):
    e = pages.extensions.open()
    with step("1. Details", expected="description + version 1.0.0"):
        e.open_details(ADDON)
        web.wait_page_text("Sample add-on used by sbtest")
        web.wait_page_text("1.0.0")


@uses_addon
@pytest.mark.native
@pytest.mark.case("ADD-004")
def test_remove_addon_native_confirm(pages, native):
    e = pages.extensions.open()
    with step("1. Remove + confirm in native dialog", expected="add-on gone"):
        e.click_remove(ADDON)
        dlg = native.wait_dialog("remove_extension")
        dlg.click("Remove")
        e.wait_gone(ADDON)
