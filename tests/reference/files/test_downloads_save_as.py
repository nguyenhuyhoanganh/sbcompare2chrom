"""Reference: downloads that ask where to save (Windows "Save As" dialog)."""
import pytest

from sbtest.steps import step

pytestmark = [pytest.mark.native, pytest.mark.browser(prefs={"download.prompt_for_download": True})]


def test_save_as_with_new_name(web, native, site, downloads_dir):
    web.open(site.url("/downloads.html"))
    with step("click the link -> Save As -> new name"):
        web.click("#dl-txt")
        native.file_dialog("save").save_as(downloads_dir / "renamed.txt")
    assert web.wait_file(downloads_dir, "renamed.txt").stat().st_size == 2048


def test_save_as_into_other_folder(web, native, site, tmp_path):
    web.open(site.url("/downloads.html"))
    web.click("#dl-bin")
    native.file_dialog("save").save_as(tmp_path / "sub" / "data.bin")
    web.wait_file(tmp_path / "sub", "data.bin")


def test_save_as_cancel(web, native, site, downloads_dir):
    web.open(site.url("/downloads.html"))
    web.click("#dl-txt")
    dlg = native.file_dialog("save")
    dlg.cancel()
    dlg.wait_closed()
    assert not list(downloads_dir.glob("sample*.txt"))
