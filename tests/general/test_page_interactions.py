"""Web content interactions: JS dialogs, forms, upload, drag & drop, shadow DOM.
Cases: testcases/general/general.md. Also the reference for every web action in sbtest.core."""
import json

import pytest

from sbtest.data import files
from sbtest.steps import step


@pytest.mark.case("GEN-003")
def test_js_dialogs(web, site):
    web.open(site.url("/dialogs.html"))
    with step("alert", expected="text 'Hello alert'"):
        web.click("#alert")
        assert web.accept_alert() == "Hello alert"
    with step("confirm -> dismiss", expected="cancelled"):
        web.click("#confirm")
        web.dismiss_alert()
        web.wait_text("#result", "cancelled")
    with step("prompt -> type value", expected="prompt:Samsung"):
        web.click("#prompt")
        web.accept_alert(prompt_text="Samsung")
        web.wait_text("#result", "prompt:Samsung")


@pytest.mark.case("GEN-004")
def test_form_submit(web, site, tmp_path):
    upload = files.text_file(tmp_path, "upload_me.txt")
    web.open(site.url("/form.html"))
    with step("fill the form"):
        web.type("#name", "Tester")
        web.type("#email", "tester@example.com")
        web.type("#note", "line 1\nline 2")
        web.select("#color", text="Blue")
        web.set_checked("#agree", True)
        web.click("#size-l")
        web.upload("#file", upload)
        web.wait_text("#file-names", "upload_me.txt")
    with step("submit", expected="server echoes values"):
        web.click("#submit")
        web.wait_url("/echo")
    echoed = json.loads(web.text("body"))["form"]
    assert echoed["name"] == "Tester"
    assert echoed["color"] == "blue"
    assert echoed["agree"] == "yes"
    assert echoed["size"] == "l"


@pytest.mark.case("GEN-005")
def test_drag_and_drop_html5(web, site):
    web.open(site.url("/dragdrop.html"))
    with step("drag HTML5 item onto the drop zone", expected="dropped:html5"):
        web.drag_and_drop("#drag-html5", "#drop-html5", method="html5")
        web.wait_text("#html5-result", "dropped:html5")


def test_mouse_drag_with_actions(web, site):
    web.open(site.url("/dragdrop.html"))
    web.drag_by("#mouse-drag", 150, 40)
    web.wait_text("#mouse-result", "moved:")


def test_shadow_dom_locators(web, site):
    """Reference for the locator syntax on a page made of nested shadow roots."""
    web.open(site.url("/shadow.html"))
    assert web.text("my-app >>> #hdr") == "Header text"
    assert web.count("my-app >>> my-card") == 2
    cards = web.texts("deepcss=my-card")          # composed text: slot content + shadow button
    assert [c.split()[0:2] for c in cards] == [["First", "card"], ["Second", "card"]]
    web.click(web.find("deep=#action", within=web.find_all("my-app >>> my-card")[1]))
    assert web.attr("my-app >>> my-card:nth-of-type(2)", "clicked") == "yes"
    web.type("aria=Card field", "typed")
    assert web.value("my-app >>> my-card >>> #field") == "typed"
    assert web.exists("text=Second card")
    assert "Header text" in web.page_text()
