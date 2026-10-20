"""History sanity on Samsung Browser. Cases: testcases/history/sanity.md"""
import pytest

from sbtest.steps import step

samsung_only = pytest.mark.targets("samsung")


def visit(web, site, *titles):
    for t in titles:
        web.open(site.page(t))
        web.wait_title(t)


@samsung_only
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


@samsung_only
@pytest.mark.sanity
@pytest.mark.case("HIS-102")
def test_clear_history(web, pages, site):
    visit(web, site, "Alpha", "Beta")
    h = pages.history.open()
    h.wait_item("Alpha")
    with step("2. Clear history + confirm", expected="list empty"):
        h.clear_history()
        web.wait_until(h.is_empty, message="history empty")


@samsung_only
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


@samsung_only
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


@samsung_only
@pytest.mark.case("HIS-106")
def test_clear_browsing_data_link(web, pages):
    h = pages.history.open()
    with step("1. Click 'Clear browsing data'", expected="settings clearBrowserData"):
        web.click(h.CLEAR_DATA_LINK)
        web.switch_tab(url="clearBrowserData")
