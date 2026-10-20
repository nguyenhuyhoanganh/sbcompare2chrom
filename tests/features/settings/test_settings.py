"""Settings. Cases: testcases/settings/settings.md

UI state is asserted, and get_pref() double-checks the underlying preference.
"""
import pytest

from sbtest.steps import step

ASK_WHERE = "Ask where to save each file before downloading"


@pytest.mark.sanity
@pytest.mark.case("SET-001")
def test_toggle_ask_where_to_save(pages):
    s = pages.settings
    with step("1. Open Settings > Downloads"):
        s.open_section("downloads")
    with step("2. Turn on 'Ask where to save'", expected="toggle on + pref true"):
        s.set_toggle(ASK_WHERE, True)
    assert s.is_on(ASK_WHERE)
    assert s.get_pref("download.prompt_for_download") is True


@pytest.mark.case("SET-002")
def test_search_settings(pages, web):
    s = pages.settings.open()
    with step("1. Search 'downloads'", expected="Downloads section shown"):
        s.search("downloads")
        web.wait_until(lambda: s.web.exists(f"deepcss=cr-toggle[aria-label=\"{ASK_WHERE}\"]"),
                       message="downloads settings visible in results")


@pytest.mark.case("SET-003")
def test_setting_persists_after_restart(session, pages):
    s = pages.settings.open_section("downloads")
    with step("1. Turn on 'Ask where to save'"):
        s.set_toggle(ASK_WHERE, True)
    with step("2. Restart and reopen Settings > Downloads", expected="still on"):
        session.restart()
        s = pages.of(session.web).settings.open_section("downloads")  # page objects hold the old web
    assert s.is_on(ASK_WHERE)


@pytest.mark.case("SET-004")
def test_on_startup_specific_pages(pages):
    s = pages.settings.open_section("onStartup")
    with step("1. Choose 'Open a specific page or set of pages'", expected="radio selected, pref == 4"):
        s.choose_radio("Open a specific page or set of pages")
    assert s.get_pref("session.restore_on_startup") == 4
