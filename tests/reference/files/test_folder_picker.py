"""Reference: Windows folder picker - Settings > Downloads > Location "Change".
(Also used by add-ons "Load unpacked": pages.extensions.load_unpacked.)"""
import pytest

from sbtest.steps import step

pytestmark = pytest.mark.native


def test_change_download_folder(pages, native, tmp_path):
    target = tmp_path / "new_downloads"
    target.mkdir()
    s = pages.settings.open_section("downloads")
    with step("Change -> folder picker -> choose folder", expected="location updated"):
        s.click_text("Change")
        native.file_dialog("open").select_folder(target)
    s.web.wait_until(lambda: s.get_pref("download.default_directory") == str(target),
                     message="download.default_directory updated")
