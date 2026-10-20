"""<Area> of <feature>. Cases: testcases/<feature>/<file>.md

Copy to tests/features/<feature>/test_<area>.py, keep only what you need.
"""
import pytest

from sbtest.steps import step
from sbtest.utils import unique


@pytest.mark.case("XX-001")
# @pytest.mark.sanity                          # part of the quick pass
# @pytest.mark.native                          # any step uses `native`
# @pytest.mark.browser(bookmarks="seed_basic", prefs={...}, extensions=["sample_addon"])
def test_what_it_verifies(web, pages, site):   # + native, session, downloads_dir, data, tmp_path
    name = unique("Item")                      # values the test creates

    with step("1. <doc step 1>"):
        pages.bookmarks.open()

    with step("2. <doc step 2>", expected="<doc expected result>"):
        pages.bookmarks.add_folder(name)

    # Expected results of the doc as assertions on state
    assert name in pages.bookmarks.titles()
