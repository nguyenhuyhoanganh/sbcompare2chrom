"""Add-on install flows (native: folder picker, OS drag & drop, store prompt).
Cases: cases/addons/addons.md (ADD-020..022). Selectors/labels must match the Samsung build."""
import pytest

from sbtest.steps import step

pytestmark = pytest.mark.native


@pytest.mark.case("ADD-020")
def test_load_unpacked(pages, native, data, cfg):
    d = data("addons")["sample"]
    e = pages.extensions.open()
    with step("1-2. Developer mode, Load unpacked, choose the folder", expected="add-on listed and enabled"):
        e.load_unpacked(native, cfg.path("paths.extensions") / d["folder"])
        info = e.wait_installed(d["name"])
    assert info["state"] == "ENABLED"


@pytest.mark.case("ADD-021")
def test_drop_crx(pages, native, data, cfg):
    d = data("addons")["sample"]
    e = pages.extensions.open()
    with step("1-3. Developer mode, drop the .crx from Explorer, confirm", expected="add-on installed"):
        e.drop_crx(native, cfg.path("paths.extensions") / d["crx"])
        e.wait_installed(d["name"])


@pytest.mark.slow
@pytest.mark.case("ADD-022")
def test_install_from_web_store(pages, native, data):
    d = data("addons")["webstore"]
    with step("1-2. Store page, Add, confirm prompt", expected="store shows it installed"):
        pages.webstore.install(d["id"], native)
    with step("check the add-ons page", expected="listed"):
        pages.extensions.open().wait_installed(d["name"])
