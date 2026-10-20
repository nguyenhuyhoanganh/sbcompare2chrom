"""Reference: "Save page as" from the keyboard shortcut and from the native context menu."""
import pytest

pytestmark = pytest.mark.native


def test_ctrl_s_save_page(web, native, site, tmp_path):
    web.open(site.url("/pages/page1.html"))
    native.hotkey("^s")
    native.file_dialog("save").save_as(tmp_path / "page1.html")
    web.wait_file(tmp_path, "page1.html")


def test_context_menu_save_as(web, native, site, tmp_path):
    web.open(site.url("/pages/page2.html"))
    native.context_menu_web(web, "#body", "Save as")
    native.file_dialog("save").save_as(tmp_path / "page2.html")
    web.wait_file(tmp_path, "page2.html")
