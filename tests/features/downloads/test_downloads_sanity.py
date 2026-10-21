"""Downloads sanity on Samsung Browser. Cases: testcases/downloads/sanity.md"""
import pytest

from sbtest.steps import step



def download(web, site, downloads_dir, link_id, name):
    web.open(site.url("/downloads.html"))
    web.click(f"#{link_id}")
    return web.wait_file(downloads_dir, name, timeout=web.long_timeout)


@pytest.mark.sanity
@pytest.mark.case("DL-101")
def test_entry_details(web, pages, site, downloads_dir):
    f = download(web, site, downloads_dir, "dl-txt", "sample.txt")
    d = pages.downloads.open()
    with step("2. Check the row", expected="name, size 2.05 KB, source 127.0.0.1"):
        info = d.wait_complete("sample.txt")
        assert info["size"] == "2.05 KB"
        assert "127.0.0.1" in info["url"]
    assert f.stat().st_size == 2048


@pytest.mark.case("DL-102")
def test_category_filter(web, pages, site, downloads_dir):
    download(web, site, downloads_dir, "dl-txt", "sample.txt")
    download(web, site, downloads_dir, "dl-bin", "data.bin")
    download(web, site, downloads_dir, "dl-png", "photo.png")
    d = pages.downloads.open()
    d.wait_item("photo.png")
    for category, expected in (("Document", ["sample.txt"]), ("Others", ["data.bin"]), ("Image", ["photo.png"]),
                               ("Video", [])):
        with step(f"2. Filter {category}", expected=f"{expected}"):
            d.filter_category(category)
            web.wait_until(lambda: sorted(d.names()) == expected, message=f"{category} lists {expected}")


@pytest.mark.case("DL-103")
def test_search(web, pages, site, downloads_dir):
    download(web, site, downloads_dir, "dl-txt", "sample.txt")
    download(web, site, downloads_dir, "dl-bin", "data.bin")
    d = pages.downloads.open()
    d.wait_item("sample.txt")
    with step("2. Search 'data'", expected="only data.bin"):
        d.search("data")
        web.wait_until(lambda: d.names() == ["data.bin"], message="only data.bin listed")


@pytest.mark.sanity
@pytest.mark.case("DL-104")
def test_cancel_in_progress(web, pages, site, downloads_dir):
    web.open(site.url("/downloads.html"))
    web.click("#dl-slow")
    d = pages.downloads.open()
    d.wait_item("slow.bin")
    with step("2. Cancel", expected="row removed + 'slow.bin removed from Downloads.' with Undo"):
        d.action("slow.bin", "Cancel")
        d.wait_item("slow.bin", present=False)
        assert "removed" in d.wait_toast("slow.bin")
    assert not (downloads_dir / "slow.bin").exists()


@pytest.mark.native
@pytest.mark.case("DL-105")
def test_ctrl_j_opens_downloads(web, native, cfg):
    with step("1. Ctrl+J", expected="Downloads page"):
        native.hotkey("^j")
        web.switch_tab(url=cfg.page_url("downloads"))  # opens in a new tab


@pytest.mark.native
@pytest.mark.case("DL-106")
def test_show_in_folder(web, native, pages, site, downloads_dir):
    download(web, site, downloads_dir, "dl-txt", "sample.txt")
    d = pages.downloads.open()
    d.wait_complete("sample.txt")
    with step("2. Show in folder", expected="Explorer with sample.txt selected"):
        d.action("sample.txt", "Show in folder")
        explorer = native.wait_explorer(downloads_dir.name)
    try:
        web.wait_until(lambda: native.explorer_has_selected(explorer, "sample.txt"), message="sample.txt selected")
    finally:
        explorer.close()


@pytest.mark.case("DL-107")
def test_remove_and_undo(web, pages, site, downloads_dir):
    download(web, site, downloads_dir, "dl-png", "photo.png")
    d = pages.downloads.open()
    d.wait_item("photo.png")
    with step("2a. X on the row", expected="row gone"):
        d.remove("photo.png")
    with step("2b. Undo", expected="row back"):
        d.toast_action("Undo")
        d.wait_item("photo.png")


@pytest.mark.sanity
@pytest.mark.case("DL-108")
def test_duplicate_name(web, pages, site, downloads_dir):
    download(web, site, downloads_dir, "dl-txt", "sample.txt")
    with step("1. Download sample.txt again", expected="saved as 'sample (1).txt'"):
        web.click("#dl-txt")
        web.wait_file(downloads_dir, "sample (1).txt")
    d = pages.downloads.open()
    d.wait_item("sample (1).txt")
    assert "sample.txt" in d.names()


@pytest.mark.native
@pytest.mark.case("DL-109")
def test_copy_link(web, pages, site, downloads_dir):
    from pywinauto import clipboard

    download(web, site, downloads_dir, "dl-txt", "sample.txt")
    d = pages.downloads.open()
    url = d.wait_complete("sample.txt")["url"]
    with step("2. Copy link", expected="clipboard = download address"):
        d.action("sample.txt", "Copy link")
        web.wait_until(lambda: clipboard.GetData() == url, message="download address on the clipboard")


@pytest.mark.native
@pytest.mark.case("DL-110")
def test_toolbar_bubble(web, native, site, downloads_dir):
    with step("1. Download sample.txt", expected="bubble: 'sample.txt 2,048 B • Done'"):
        download(web, site, downloads_dir, "dl-txt", "sample.txt")
        row = native.element({**native.criteria("download_bubble_item"), "title_re": r"^sample\.txt "})
    assert "Done" in row.element_info.name and "2,048 B" in row.element_info.name, row.element_info.name


@pytest.mark.case("DL-111")
def test_download_attribute(web, pages, site, downloads_dir):
    with step("1. Click the link with download='saved-page1.html'", expected="saved under that name"):
        download(web, site, downloads_dir, "dl-attr", "saved-page1.html")
    pages.downloads.open().wait_item("saved-page1.html")
