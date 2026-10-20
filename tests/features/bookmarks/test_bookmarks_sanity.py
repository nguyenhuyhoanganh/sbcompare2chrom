"""Bookmarks sanity on Samsung Browser. Cases: testcases/bookmarks/sanity.md"""
import pytest

from sbtest.steps import step
from sbtest.utils import unique

samsung_only = pytest.mark.targets("samsung")


@pytest.mark.sanity
@pytest.mark.case("BM-103")
@pytest.mark.browser(bookmarks="seed_basic")
def test_edit_name_and_url(pages, site):
    bm = pages.bookmarks.open()
    name, url = unique("Edited"), site.url("/pages/page3.html")
    with step("2-3. Edit 'Static page 1': new name + web address, Save", expected="list updated"):
        bm.edit("Static page 1", name=name, url=url)
    assert "Static page 1" not in bm.titles()
    assert bm.item_url(name) == url


@samsung_only
@pytest.mark.case("BM-104")
@pytest.mark.browser(bookmarks="seed_basic")
def test_edit_from_context_menu(pages):
    bm = pages.bookmarks.open()
    name = unique("Renamed")
    with step("2. Right click 'Static page 2'", expected="Edit, Delete, Open all ... entries"):
        bm.item_menu("Static page 2", "Edit")
        bm.open_dialog()
    with step("2b. Change the name, Save", expected="new name listed"):
        bm._fill_edit_dialog(name, None)
        bm.save_dialog()
        bm.wait_item(name)


@samsung_only
@pytest.mark.sanity
@pytest.mark.case("BM-105")
@pytest.mark.browser(bookmarks="seed_basic")
def test_delete_from_context_menu_and_undo(pages):
    bm = pages.bookmarks.open()
    with step("2. Right click 'Static page 2' > Delete", expected="gone + '1 bookmark deleted'"):
        bm.item_menu("Static page 2", "Delete")
        bm.wait_item("Static page 2", present=False)
        assert "1 bookmark deleted" in bm.wait_toast("deleted")
    with step("3. Undo", expected="back in the list"):
        bm.undo()
        bm.wait_item("Static page 2")


@samsung_only
@pytest.mark.case("BM-106")
@pytest.mark.browser(bookmarks="seed_basic")
def test_select_all_and_delete(pages, web):
    bm = pages.bookmarks.open()
    with step("2a. Select all", expected="'3 selected'"):
        bm.toolbar("Select all")
        web.wait_until(lambda: all(bm.is_selected(t) for t in ("Static page 1", "Static page 2", "Work")),
                       message="all rows ticked")
        assert "3 selected" in web.text("bookmarks-app >>> bookmarks-toolbar >>> #overlay >>> #number-selected")
    with step("2b. Delete", expected="list empty, snack bar"):
        toast = bm.delete_selected()
        web.wait_until(lambda: not bm.titles(), message="bookmark list empty")
    assert "deleted" in toast.lower()


@pytest.mark.sanity
@pytest.mark.case("BM-107")
@pytest.mark.browser(bookmarks="seed_basic")
def test_open_bookmark(pages, web):
    bm = pages.bookmarks.open()
    with step("2. Click 'Static page 1'", expected="page loaded (new tab on Samsung)"):
        bm.open_item("Static page 1")
        web.switch_tab(title="Static page 1")


@pytest.mark.sanity
@pytest.mark.case("BM-108")
@pytest.mark.browser(bookmarks="seed_basic")
def test_bookmarks_survive_restart(session, pages):
    bm = pages.bookmarks.open()
    folder, name = unique("Kept folder"), unique("Kept name")
    with step("1. Add a folder, rename 'Static page 1'"):
        bm.add_folder(folder)
        bm.edit("Static page 1", name=name)
    with step("2-3. Restart, open the bookmark manager", expected="both still listed"):
        session.restart()
        bm = pages.of(session.web).bookmarks.open()
        bm.wait_item(folder)
        bm.wait_item(name)


@pytest.mark.case("BM-109")
@pytest.mark.browser(bookmarks="seed_basic")
def test_add_bookmark_into_folder(pages, site):
    bm = pages.bookmarks.open()
    name, url = unique("In Work"), site.page("In Work page")
    with step("1. Select folder 'Work'"):
        bm.open_folder("Work")
    with step("2. Add bookmark: name + address, Save", expected="listed in Work with its address"):
        bm.add_bookmark(name, url)
        assert bm.item_url(name) == url
    with step("check the bookmarks bar folder", expected="not listed there"):
        bm.open_folder(bm.BAR_FOLDER)
        bm.wait_item("Static page 1")
        assert name not in bm.titles()


@samsung_only
@pytest.mark.case("BM-110")
@pytest.mark.browser(bookmarks="seed_many")
def test_sort_by_name(pages):
    bm = pages.bookmarks.open()
    bm.wait_titles(["Alpha", "Beta", "Gamma", "Delta", "Folder X"])
    with step("2. Right ⋮ > Sort by name", expected="folders first, then A-Z"):
        bm.options("Sort by name")
        bm.wait_titles(["Folder X", "Alpha", "Beta", "Delta", "Gamma"])


@samsung_only
@pytest.mark.sanity
@pytest.mark.case("BM-111")
@pytest.mark.browser(bookmarks="seed_basic")
def test_delete_folder_and_undo(pages, web):
    bm = pages.bookmarks.open()
    with step("1. Delete folder 'Work'", expected="gone from list and tree"):
        bm.delete("Work")
        web.wait_until(lambda: "Work" not in bm.folders(), message="'Work' gone from the tree")
    with step("2. Undo", expected="'Work' back with its 2 bookmarks"):
        bm.undo()
        bm.wait_item("Work")
        bm.open_folder("Work")
        bm.wait_titles(["Form page", "Dialogs page"])


@samsung_only
@pytest.mark.case("BM-112")
@pytest.mark.browser(bookmarks="seed_basic")
def test_open_all_in_new_tabs(pages, web):
    bm = pages.bookmarks.open()
    before = web.tabs
    with step("1. Right click 'Work' > Open all (2) in new tab", expected="2 new tabs"):
        bm.item_menu("Work", "Open all (2) in new tab")
        web.wait_until(lambda: len(web.tabs) == len(before) + 2, message="2 new tabs")
    web.switch_tab(title="Form page")
    web.switch_tab(title="Dialogs page")


@samsung_only
@pytest.mark.native
@pytest.mark.case("BM-113")
@pytest.mark.browser(bookmarks="seed_basic")
def test_export_bookmarks(pages, native, web, site, tmp_path):
    bm = pages.bookmarks.open()
    target = tmp_path / "exported_bookmarks.html"
    with step("1-2. Left ⋮ > Export bookmarks, Save As", expected="HTML file written"):
        bm.export(native, target)
        web.wait_file(tmp_path, target.name)
    html = target.read_text(encoding="utf-8", errors="ignore")
    for text in ("Static page 1", "Static page 2", "Work", site.url("/pages/page1.html")):
        assert text in html, text


@samsung_only
@pytest.mark.case("BM-114")
def test_import_opens_settings(pages, web):
    bm = pages.bookmarks.open()
    with step("1. Left ⋮ > Import bookmarks", expected="Settings import page"):
        bm.organize("Import bookmarks")
        web.switch_tab(url="settings")
