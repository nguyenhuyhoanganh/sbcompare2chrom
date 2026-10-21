"""History sanity on Samsung Browser. Cases: cases/history/sanity.md"""
import pytest

from sbtest.steps import step



def visit(web, site, *titles):
    for t in titles:
        web.open(site.page(t))
        web.wait_title(t)


@pytest.mark.sanity
@pytest.mark.case("HIS-101")
def test_entry_details(web, pages, site):
    visit(web, site, "Alpha", "Beta")
    h = pages.history.open()
    h.wait_item("Alpha")
    rows = {r["title"]: r for r in h.rows()}
    with step("2. Check the entries", expected="Beta above Alpha, domain + time, 'Today' header"):
        assert h.titles().index("Beta") < h.titles().index("Alpha")
        assert rows["Alpha"]["domain"] == "127.0.0.1" and rows["Alpha"]["time"]
        assert any(d.startswith("Today") for d in h.days())


@pytest.mark.sanity
@pytest.mark.case("HIS-102")
def test_clear_history(web, pages, site):
    visit(web, site, "Alpha", "Beta")
    h = pages.history.open()
    h.wait_item("Alpha")
    with step("2. Clear history + confirm", expected="list empty"):
        h.clear_history()
        web.wait_until(h.is_empty, message="history empty")


@pytest.mark.case("HIS-103")
def test_time_filter(web, pages, site):
    visit(web, site, "Alpha")
    h = pages.history.open()
    h.wait_item("Alpha")
    with step("2a. Only 'Last hour' ticked", expected="Alpha listed"):
        h.filter_time("Last hour")
        h.wait_item("Alpha")
    with step("2b. Only 'Yesterday' ticked", expected="nothing listed"):
        h.filter_time("Yesterday")
        h.wait_item("Alpha", present=False)
    with step("2c. 'Yesterday' + 'Today' ticked", expected="Alpha listed (filters add up)"):
        h.filter_time("Yesterday", "Today")
        h.wait_item("Alpha")
    with step("2d. All time", expected="Alpha listed"):
        h.filter_time("All time")
        h.wait_item("Alpha")


@pytest.mark.case("HIS-104")
def test_delete_whole_day(web, pages, site):
    visit(web, site, "Alpha", "Beta")
    h = pages.history.open()
    h.wait_item("Alpha")
    with step("2. Tick the 'Today' header, Delete", expected="both entries gone"):
        web.click(web.find("deep=#all-select", within=h.items()[0]))
        h.delete_selected()
        web.wait_until(h.is_empty, message="history empty")


@pytest.mark.sanity
@pytest.mark.case("HIS-105")
def test_history_survives_restart(session, web, pages, site):
    visit(web, site, "Alpha")
    with step("2-3. Restart, open History", expected="Alpha listed"):
        session.restart()
        pages.of(session.web).history.open().wait_item("Alpha")


@pytest.mark.case("HIS-106")
def test_clear_browsing_data_link(web, pages):
    h = pages.history.open()
    with step("1. Click 'Clear browsing data'", expected="settings clearBrowserData"):
        web.click(h.CLEAR_DATA_LINK)
        web.switch_tab(url="clearBrowserData")


@pytest.mark.case("HIS-107")
def test_search_no_match(web, pages, site):
    visit(web, site, "Alpha")
    h = pages.history.open()
    h.wait_item("Alpha")
    with step("2. Search 'zzzz'", expected="nothing listed"):
        h.search("zzzz")
        web.wait_until(lambda: not h.titles(), message="no entry listed")


@pytest.mark.case("HIS-108")
def test_cancel_selection(web, pages, site):
    visit(web, site, "Alpha")
    h = pages.history.open()
    h.wait_item("Alpha")
    tick = lambda: web.find("deep=si-select#select", within=h.item("Alpha"))  # noqa: E731
    with step("1. Tick Alpha", expected="Delete enabled"):
        h.select("Alpha")
        web.wait_until(lambda: h.toolbar_enabled("Delete"), message="Delete enabled")
    with step("2. Cancel (<)", expected="nothing ticked, Delete disabled"):
        h.cancel_selection()
        web.wait_until(lambda: not web.is_checked(tick()), message="Alpha unticked")
        assert not h.toolbar_enabled("Delete")


@pytest.mark.case("HIS-109")
def test_revisit_moves_to_top(web, pages, site):
    visit(web, site, "Alpha", "Beta", "Alpha")
    h = pages.history.open()
    h.wait_item("Beta")
    with step("2. Open History", expected="Alpha above Beta"):
        titles = h.titles()
        assert titles.index("Alpha") < titles.index("Beta"), titles
