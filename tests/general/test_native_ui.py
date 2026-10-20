"""Browser UI and OS dialogs through pywinauto (Windows only). Cases: testcases/general/general.md"""
import pytest

from sbtest.steps import step

pytestmark = pytest.mark.native


@pytest.mark.case("GEN-010")
def test_omnibox_navigation(web, native, site):
    url = site.url("/pages/page2.html")
    with step("type URL in the omnibox + Enter", expected="page loads"):
        native.navigate(url)
        web.wait_title("Static page 2")
    assert "page2.html" in native.omnibox_text()


@pytest.mark.case("GEN-011")
def test_save_page_as(web, native, site, tmp_path):
    web.open(site.url("/pages/page1.html"))
    with step("Ctrl+S -> Save As -> temp folder", expected=".html saved"):
        native.hotkey("^s")
        target = native.file_dialog("save").save_as(tmp_path / "saved_page.html")
        web.wait_file(tmp_path, "saved_page.html")
    assert target.exists()


def test_native_context_menu_open_in_new_tab(web, native, site):
    web.open(site.url("/popups.html"))
    before = web.tabs
    native.context_menu_web(web, "#same-link", "Open link in new tab")
    web.wait_new_tab(before, switch=False)
