"""Add-ons sanity on Samsung Browser. Cases: cases/addons/sanity.md"""
import pytest

from sbtest.steps import step

ADDON = "SB Sample Addon"
uses_addon = pytest.mark.browser(extensions=["sample_addon"])


def page_marked(web, site) -> bool:
    web.open(site.url("/index.html"))
    return web.js("return document.documentElement.getAttribute('data-sb-addon')") == "active"


@uses_addon
@pytest.mark.sanity
@pytest.mark.case("ADD-101")
def test_card_details(pages, web):
    e = pages.extensions.open()
    card = e.item(ADDON)
    with step("1. Check the card", expected="name, description, Details/Remove, on"):
        assert "Sample add-on used by sbtest" in web.text(web.find("deep=#description", within=card))
        assert e.find_by_text("si-flat-button", "Details", within=card)
        assert e.find_by_text("si-flat-button", "Remove", within=card)
        assert e.is_enabled(ADDON)
    with step("2. Developer mode on", expected="version 1.0.0 shown"):
        e.set_dev_mode(True)
        assert web.text(web.find("deep=#version", within=e.item(ADDON))) == "1.0.0"


@pytest.mark.sanity
@pytest.mark.case("ADD-102")
def test_developer_mode_toolbar(pages, web):
    e = pages.extensions.open()
    tools = {"Load Unpacked", "Pack add-on", "Update"}
    with step("1. Developer mode on", expected="Load Unpacked, Pack add-on, Update"):
        e.set_dev_mode(True)
        web.wait_until(lambda: tools <= set(e.dev_toolbar()), message="developer tools shown")
    with step("2. Developer mode off", expected="tools hidden"):
        e.set_dev_mode(False)
        web.wait_until(lambda: not (tools & set(e.dev_toolbar())), message="developer tools hidden")


@uses_addon
@pytest.mark.case("ADD-103")
def test_search(pages, web):
    e = pages.extensions.open()
    with step("1a. Search 'Sample'", expected="add-on listed"):
        e.search("Sample")
        web.wait_until(lambda: e.names() == [ADDON], message="add-on listed")
    with step("1b. Search 'zzz'", expected="nothing listed"):
        e.search("zzz")
        web.wait_until(lambda: e.names() == [], message="nothing listed")


@uses_addon
@pytest.mark.sanity
@pytest.mark.case("ADD-104")
def test_disabled_survives_restart(session, pages, web, site):
    e = pages.extensions.open()
    with step("1. Turn the add-on off"):
        e.set_enabled(ADDON, False)
    with step("2. Restart, open Add-ons", expected="still off, page not marked"):
        session.restart()
        e = pages.of(session.web).extensions.open()
        assert not e.is_enabled(ADDON)
        assert not page_marked(session.web, site)


@uses_addon
@pytest.mark.native
@pytest.mark.case("ADD-105")
def test_cancel_remove(pages, native):
    e = pages.extensions.open()
    with step("1-2. Remove, then Cancel in 'Delete SB Sample Addon?'", expected="still installed"):
        e.click_remove(ADDON)
        dlg = native.wait_dialog("remove_extension")
        dlg.click("Cancel")
        dlg.wait_closed()
    assert ADDON in [x["name"] for x in e.info()]
    assert e.is_enabled(ADDON)


@uses_addon
@pytest.mark.case("ADD-107")
def test_keyboard_shortcuts(pages, web):
    e = pages.extensions.open()
    with step("1. Keyboard shortcuts", expected="'Activate add-on for SB Sample Addon': Not set"):
        e.open_shortcuts()
        web.wait_until(lambda: e.shortcuts().get(f"Activate add-on for {ADDON}") == "Not set",
                       message="shortcut listed as Not set")
        assert web.find(f'deepcss=[aria-label="Edit shortcut Activate add-on for {ADDON}"]')


@pytest.mark.sanity
@pytest.mark.case("ADD-108")
def test_pack_creates_crx(pages, web, tmp_path):
    import shutil

    from sbtest.config import EXTENSIONS_DIR

    src = tmp_path / "addon"
    shutil.copytree(EXTENSIONS_DIR / "sample_addon", src)
    e = pages.extensions.open()
    with step("1. Developer mode, Pack add-on", expected="'Pack extension' disabled while the directory is empty"):
        e.open_pack_dialog()
        assert not e.pack_button_enabled()
    with step("2. Root directory, Pack extension", expected="addon.crx + addon.pem next to the folder"):
        web.type(e.pack_inputs()[0], str(src))
        web.wait_until(e.pack_button_enabled, message="Pack extension enabled")
        e.dialog_button("Pack extension")
        web.wait_file(tmp_path, "addon.crx")
        web.wait_file(tmp_path, "addon.pem")


@uses_addon
@pytest.mark.case("ADD-109")
def test_reload_unpacked(pages, web, site):
    e = pages.extensions.open()
    e.set_dev_mode(True)
    with step("1. Reload icon", expected="still enabled"):
        web.click(web.find("deep=#dev-reload-button", within=e.item(ADDON)))
        web.wait_until(lambda: e.is_enabled(ADDON), message="enabled after reload")
    with step("2. Open a local page", expected="content script still runs"):
        web.wait_until(lambda: page_marked(web, site), message="content script ran")


@pytest.mark.slow
@pytest.mark.case("ADD-110")
def test_get_addons_opens_store(pages, web):
    e = pages.extensions.open()
    with step("1. Get add-ons", expected="Chrome Web Store extensions page in a new tab"):
        e.get_addons()
        web.wait_url("chromewebstore.google.com")
