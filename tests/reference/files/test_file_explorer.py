"""Reference: File Explorer <-> browser - real OS drag of a file onto a page, and
"Show in folder" opening Explorer with the downloaded file selected."""
import pytest

from sbtest.data import files
from sbtest.steps import step

pytestmark = pytest.mark.native


def test_drag_file_from_explorer_to_drop_zone(web, native, site, tmp_path):
    f = files.text_file(tmp_path, "dragged.txt")
    web.open(site.url("/upload.html"))
    with step("drag the file from Explorer onto the drop zone"):
        native.drag_file_from_explorer(f, web=web, target="#drop-zone")
    web.wait_text("#dropped", "dragged.txt")


def test_show_in_folder_opens_explorer(web, native, pages, site, downloads_dir):
    web.open(site.url("/downloads.html"))
    web.click("#dl-txt")
    web.wait_file(downloads_dir, "sample.txt")
    d = pages.downloads.open()
    with step("Show in folder", expected="Explorer opens with the file selected"):
        d.action("sample.txt", "Show in folder")
        explorer = native.wait_explorer(downloads_dir.name)
    try:
        assert "sample.txt" in native.explorer_selected(explorer)
    finally:
        explorer.close()
