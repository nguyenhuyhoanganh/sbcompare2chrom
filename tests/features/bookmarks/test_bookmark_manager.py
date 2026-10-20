"""Bookmark manager - web layer only (runs headless too). Cases: testcases/bookmarks/bookmark_manager.md"""
import pytest

from sbtest.steps import step
from sbtest.utils import unique


@pytest.mark.sanity
@pytest.mark.case("BM-001")
def test_add_bookmark(pages, site):
    bm = pages.bookmarks
    name = unique("Bookmark")
    with step("1. Open the bookmark manager"):
        bm.open()
    with step("2-3. Organize > Add new bookmark, fill name + URL, Save",
              expected="the bookmark is listed"):
        bm.add_bookmark(name, site.page("New"))
    assert name in bm.titles()


@pytest.mark.case("BM-002")
def test_add_folder(pages):
    bm = pages.bookmarks
    folder = unique("Folder")
    with step("1. Open the bookmark manager"):
        bm.open()
    with step("2. Organize > Add new folder", expected="folder in list and tree"):
        bm.add_folder(folder)
    assert folder in bm.titles()
    assert folder in bm.folders()


@pytest.mark.case("BM-003")
@pytest.mark.browser(bookmarks="seed_basic")
def test_edit_bookmark(pages):
    bm = pages.bookmarks
    new_name = unique("Renamed")
    with step("1. Open the bookmark manager"):
        bm.open()
    with step("2-3. Edit 'Static page 1' -> new name", expected="new name shown, old gone"):
        bm.edit("Static page 1", name=new_name)
    titles = bm.titles()
    assert new_name in titles
    assert "Static page 1" not in titles


@pytest.mark.sanity
@pytest.mark.case("BM-004")
@pytest.mark.browser(bookmarks="seed_basic")
def test_delete_and_undo(pages):
    bm = pages.bookmarks
    with step("1. Open the bookmark manager"):
        bm.open()
    with step("2. Delete 'Static page 2'", expected="item gone + toast"):
        toast = bm.delete("Static page 2")
    assert "deleted" in toast.lower()
    with step("3. Undo", expected="item is back"):
        bm.undo()
        bm.wait_item("Static page 2")


@pytest.mark.case("BM-005")
@pytest.mark.browser(bookmarks="seed_many")
def test_search(pages):
    bm = pages.bookmarks
    with step("1. Open the bookmark manager"):
        bm.open()
    with step("2. Search 'ta'", expected="Beta, Delta"):
        bm.search("ta")
        bm.wait_titles(["Beta", "Delta"])


@pytest.mark.case("BM-006")
@pytest.mark.browser(bookmarks="seed_basic")
def test_open_folder(pages):
    bm = pages.bookmarks
    with step("1. Open the manager and select folder 'Work'"):
        bm.open()
        bm.open_folder("Work")
    bm.wait_titles(["Form page", "Dialogs page"])
