"""Reference: every kind of input, select, checkbox/radio, contenteditable and keyboard keys."""
import json

from sbtest.data import files
from sbtest.web import Keys


def test_text_inputs(web, site):
    web.open(site.url("/inputs.html"))
    assert web.value("#text") == "initial"
    web.type("#text", "replaced")                  # clears first
    assert web.value("#text") == "replaced"
    web.type("#text", " + more", clear=False)
    assert web.value("#text") == "replaced + more"
    web.clear("#text")
    assert web.value("#text") == ""
    web.type("#number", "7")
    web.set_value("#date", "2026-10-20")           # inputs that ignore typing: JS + events
    assert web.value("#date") == "2026-10-20"
    assert not web.is_enabled("#disabled")


def test_range_and_multi_select(web, site):
    web.open(site.url("/inputs.html"))
    web.set_value("#range", "75")
    web.wait_text("#range-value", "75")
    web.select("#multi", text="Banana")
    web.select("#multi", value="d")
    chosen = web.js("return Array.from(arguments[0].selectedOptions).map(o => o.value)", web.find("#multi"))
    assert chosen == ["b", "d"]


def test_contenteditable(web, site):
    web.open(site.url("/inputs.html"))
    web.click("#editor")
    web.press("Hello editor")
    assert web.text("#editor") == "Hello editor"


def test_keys_and_chords(web, site):
    web.open(site.url("/inputs.html"))
    web.click("#keys")
    web.press("ENTER")
    web.wait_text("#last-key", "Enter", contains=False)
    web.press(Keys.CONTROL, "a")
    web.wait_text("#last-key", "ctrl+a", contains=False)
    web.press(Keys.SHIFT, Keys.TAB)                 # focus moves back
    web.wait_text("#last-key", "shift+Tab", contains=False)
    assert web.focused().get_attribute("id") != "keys"


def test_form_submit_with_all_controls(web, site, tmp_path):
    upload = files.text_file(tmp_path, "upload_me.txt", "abc")
    web.open(site.url("/form.html"))
    web.type("#name", "Tester")
    web.type("#email", "tester@example.com")
    web.type("#password", "secret")
    web.type("#note", "line 1\nline 2")
    web.select("#color", text="Blue")
    web.set_checked("#agree", True)
    web.click("#size-l")
    web.upload("#file", upload)
    web.wait_text("#file-names", "upload_me.txt")
    web.click("#submit")
    web.wait_url("/upload")
    echoed = json.loads(web.text("body"))
    assert echoed["fields"]["name"] == "Tester" and echoed["fields"]["color"] == "blue"
    assert echoed["fields"]["agree"] == "yes" and echoed["fields"]["size"] == "l"
    assert echoed["files"] == [{"field": "file", "name": "upload_me.txt", "size": 3}]
