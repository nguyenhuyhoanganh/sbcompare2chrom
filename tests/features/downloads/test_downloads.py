"""Downloads. Cases: cases/downloads/downloads.md

Files are served by the local site (site.download(...)) and land in the session's own
download folder (downloads_dir), so checks on disk are deterministic.
"""
import pytest

from sbtest.steps import step


def start_download(web, site, link_id):
    web.open(site.url("/downloads.html"))
    web.click(f"#{link_id}")


@pytest.mark.sanity
@pytest.mark.case("DL-001")
def test_download_file(web, pages, site, downloads_dir):
    with step("1. Click sample.txt on the downloads test page", expected="file on disk, 2048 bytes"):
        start_download(web, site, "dl-txt")
        f = web.wait_file(downloads_dir, "sample.txt", timeout=web.long_timeout)
    assert f.stat().st_size == 2048
    with step("2. Open Downloads", expected="sample.txt listed"):
        pages.downloads.open()
        pages.downloads.wait_complete("sample.txt")


@pytest.mark.case("DL-002")
def test_remove_entry_keeps_file(web, pages, site, downloads_dir):
    start_download(web, site, "dl-txt")
    f = web.wait_file(downloads_dir, "sample.txt")
    d = pages.downloads.open()
    with step("2. Delete from history", expected="entry gone, file stays"):
        d.remove("sample.txt")
    assert f.exists()


@pytest.mark.native
@pytest.mark.case("DL-003")
def test_clear_all(web, native, pages, site, downloads_dir):
    with step("1. Download two files, open Downloads"):
        start_download(web, site, "dl-txt")
        web.wait_file(downloads_dir, "sample.txt")
        start_download(web, site, "dl-bin")
        web.wait_file(downloads_dir, "data.bin")
        d = pages.downloads.open()
        d.wait_item("data.bin")
    with step("2. Close the Downloads bubble with its X", expected="bubble gone, Clear all visible"):
        native.close_download_bubble()
    with step("3. Clear all", expected="list empty"):
        d.clear_all()


@pytest.mark.slow
@pytest.mark.case("DL-004")
def test_pause_resume(web, pages, site, downloads_dir):
    start_download(web, site, "dl-slow")
    d = pages.downloads.open()
    d.wait_item("slow.bin")
    with step("2a. Pause", expected="status Paused"):
        d.action("slow.bin", "Pause")
        web.wait_until(lambda: "paused" in d.status("slow.bin").lower(), message="Paused status")
    with step("2b. Resume", expected="download completes"):
        d.action("slow.bin", "Resume")
        d.wait_complete("slow.bin", timeout=120)
    assert (downloads_dir / "slow.bin").stat().st_size == 10 * 1024 * 1024


@pytest.mark.native
@pytest.mark.case("DL-005")
@pytest.mark.browser(prefs={"download.prompt_for_download": True})
def test_save_as_dialog(web, native, site, downloads_dir):
    with step("1. Click sample.txt", expected="Save As dialog"):
        start_download(web, site, "dl-txt")
        dlg = native.file_dialog("save")
    with step("2. Save as renamed.txt", expected="file saved with that name"):
        dlg.save_as(downloads_dir / "renamed.txt")
        web.wait_file(downloads_dir, "renamed.txt")
