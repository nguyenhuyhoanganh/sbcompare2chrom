"""Navigation and tabs. Cases: testcases/general/general.md"""
import pytest

from sbtest.steps import step


@pytest.mark.sanity
@pytest.mark.case("GEN-001")
def test_back_forward(web, site):
    with step("open page 1 then page 2"):
        web.open(site.url("/pages/page1.html"))
        web.click("#next")
        web.wait_title("Static page 2")
    with step("Back", expected="page 1"):
        web.back()
        web.wait_title("Static page 1")
    with step("Forward", expected="page 2"):
        web.forward()
        web.wait_title("Static page 2")


@pytest.mark.case("GEN-002")
def test_link_opens_new_tab(web, site):
    web.open(site.url("/popups.html"))
    before = web.tabs
    with step("click target=_blank link", expected="new tab with page 2"):
        web.click("#blank-link")
        web.wait_new_tab(before)
        web.wait_title("Static page 2")
    assert len(web.tabs) == len(before) + 1
    web.close_tab()
    assert web.title == "Popups page"
