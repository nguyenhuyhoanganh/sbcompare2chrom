"""Reference: uploads and downloads without any OS dialog (web layer only).
OS dialogs / Explorer versions are in tests/reference/files/."""
import json

from sbtest.data import files


def test_upload_single_and_multiple_files(web, site, tmp_path):
    a = files.text_file(tmp_path, "a.txt", "aaa")
    b = files.png_file(tmp_path, "b.png")
    web.open(site.url("/upload.html"))
    web.upload("#file", a, b)                       # sets files on <input type=file> directly
    web.click("#submit")
    web.wait_url("/upload")
    got = json.loads(web.text("body"))
    assert [f["name"] for f in got["files"]] == ["a.txt", "b.png"]
    assert got["fields"]["note"] == "from sbtest"


def test_download_lands_in_profile_folder(web, site, downloads_dir):
    web.open(site.url("/downloads.html"))
    web.click("#dl-bin")
    f = web.wait_file(downloads_dir, "data.bin", timeout=web.long_timeout)
    assert f.stat().st_size == 100 * 1024


def test_download_attribute_and_generated_file(web, site, downloads_dir):
    web.open(site.url("/downloads.html"))
    web.click("#dl-attr")                           # <a download="saved-page1.html">
    web.wait_file(downloads_dir, "saved-page1.html")
    web.open(site.download("report.csv", 64, "text/csv"))
    assert web.wait_file(downloads_dir, "report.csv").stat().st_size == 64
