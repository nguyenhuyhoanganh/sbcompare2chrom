"""Navigation and tabs. Cases: general.md"""
import pytest

from sbtest.steps import step


@pytest.mark.sanity
@pytest.mark.case("GEN-001")
def test_back_forward(web, site):
    with step("1. Open \"Static page 1\", follow the link to \"Static page 2\""):
        web.open(site.url("/pages/page1.html"))
        web.click("#next")
        web.wait_title("Static page 2")
    with step("2. Go back, then forward", expected="page 1, then page 2 again"):
        web.back()
        web.wait_title("Static page 1")
        web.forward()
        web.wait_title("Static page 2")


@pytest.mark.native
@pytest.mark.sanity
@pytest.mark.case("GEN-002")
def test_open_link_in_new_tab(web, native, site):
    with step("1. Open \"Static page 1\""):
        web.open(site.url("/pages/page1.html"))
        web.wait_title("Static page 1")
        first = web.tabs[0]
    before = web.tabs
    with step("2. Right-click the link \"Next\" and choose \"Open in new tab\"",
              expected="a new tab with \"Static page 2\"; the first tab still shows \"Static page 1\""):
        # Samsung's label is "Open in new tab" (Chrome: "Open link in new tab"); the tab opens
        # in the background, so switch to it to read it
        native.context_menu_web(web, "#next", "Open in new tab")
        web.wait_new_tab(before)
        web.wait_title("Static page 2")
        web.switch_tab(index=web.tabs.index(first))
        assert web.title == "Static page 1"
