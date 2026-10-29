"""Add-on install flows (native: folder picker, store prompt).
Cases: addons.md (ADD-005, ADD-006). Selectors/labels must match the Samsung build."""
import pytest

from sbtest.steps import step

pytestmark = pytest.mark.native


@pytest.mark.case("ADD-005")
def test_load_unpacked(pages, native, data, cfg):
    d = data("addons")["sample"]
    e = pages.extensions.open()
    with step("1-2. Developer mode, Load unpacked, choose the folder", expected="add-on listed and enabled"):
        e.load_unpacked(native, cfg.path("paths.extensions") / d["folder"])
        info = e.wait_installed(d["name"])
    assert info["state"] == "ENABLED"


@pytest.mark.slow
@pytest.mark.case("ADD-006")
def test_install_from_web_store(pages, native, data):
    d = data("addons")["webstore"]
    with step("1-2. Store page, Add, confirm prompt",
              expected="the store shows the remove button; the add-on is listed on the add-ons page"):
        pages.webstore.install(d["id"], native)
        pages.extensions.open().wait_installed(d["name"])
