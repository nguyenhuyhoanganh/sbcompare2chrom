"""History. Cases: testcases/history/history.md

History is seeded by really visiting local pages (site.page(title) gives unique titles).
"""
import pytest

from sbtest.steps import step


def visit(web, site, *titles):
    for t in titles:
        web.open(site.page(t))
        web.wait_title(t)


@pytest.mark.sanity
@pytest.mark.case("HIS-001")
def test_visited_pages_listed(web, pages, site):
    with step("1. Visit Alpha then Beta"):
        visit(web, site, "Alpha", "Beta")
    with step("2. Open History", expected="Beta above Alpha"):
        pages.history.open()
        pages.history.wait_item("Alpha")
    titles = pages.history.titles()
    assert titles.index("Beta") < titles.index("Alpha")


@pytest.mark.case("HIS-002")
def test_search_history(web, pages, site):
    visit(web, site, "Alpha", "Beta", "Gamma")
    h = pages.history.open()
    with step("2. Search 'Gam'", expected="only Gamma"):
        h.search("Gam")
        web.wait_until(lambda: h.titles() == ["Gamma"], message="only Gamma listed")


@pytest.mark.sanity
@pytest.mark.case("HIS-003")
def test_delete_selected(web, pages, site):
    visit(web, site, "Alpha", "Beta")
    h = pages.history.open()
    h.wait_item("Alpha")
    with step("2. Select Alpha, Delete, confirm Remove", expected="Alpha gone, Beta stays"):
        h.select("Alpha")
        h.delete_selected()
        h.wait_item("Alpha", present=False)
    assert h.has_item("Beta")


@pytest.mark.case("HIS-004")
def test_remove_from_menu(web, pages, site):
    visit(web, site, "Alpha")
    h = pages.history.open()
    with step("2. Item menu > Remove from history", expected="history empty"):
        h.remove("Alpha")
    web.wait_until(h.is_empty, message="history empty")


@pytest.mark.case("HIS-005")
def test_open_from_history(web, pages, site):
    visit(web, site, "Alpha")
    h = pages.history.open()
    with step("1. Click Alpha in history", expected="Alpha loaded"):
        h.open_item("Alpha")
        web.wait_title("Alpha")


@pytest.mark.native
@pytest.mark.case("HIS-010")
def test_ctrl_h_opens_history(web, native, cfg):
    with step("1. Press Ctrl+H", expected="History opened"):
        native.hotkey("^h")
        web.switch_tab(url=cfg.page_url("history"))  # opens in a new tab
