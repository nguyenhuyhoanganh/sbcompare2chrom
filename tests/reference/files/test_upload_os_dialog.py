"""Reference: upload through the Windows "Open" dialog (page button -> hidden <input type=file>).
When the page exposes the <input>, prefer web.upload() (tests/reference/web)."""
import pytest

from sbtest.data import files
from sbtest.steps import step

pytestmark = pytest.mark.native


def test_open_dialog_single_file(web, native, site, tmp_path):
    f = files.text_file(tmp_path, "pick_me.txt")
    web.open(site.url("/upload.html"))
    with step("click the page button -> Windows Open dialog -> choose a file"):
        web.click("#pick")
        native.file_dialog("open").open(f)
    web.wait_text("#picked", "pick_me.txt")


def test_open_dialog_multiple_files(web, native, site, tmp_path):
    a = files.text_file(tmp_path, "first.txt")
    b = files.png_file(tmp_path, "second.png")
    web.open(site.url("/upload.html"))
    web.click("#pick")
    native.file_dialog("open").open(a, b)          # same folder, quoted names
    web.wait_until(lambda: sorted(web.text("#picked").split(",")) == ["first.txt", "second.png"],
                   message="both files picked")


def test_open_dialog_cancel(web, native, site):
    web.open(site.url("/upload.html"))
    web.click("#pick")
    dlg = native.file_dialog("open")
    dlg.cancel()
    dlg.wait_closed()
    assert web.text("#picked") == ""
