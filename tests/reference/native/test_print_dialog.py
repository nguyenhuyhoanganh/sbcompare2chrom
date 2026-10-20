"""Reference: print preview dialog opened by window.print()."""
import pytest

pytestmark = pytest.mark.native


def test_print_dialog_open_and_cancel(web, native, site):
    web.open(site.url("/dialogs.html"))
    web.click("#print")                           # the page calls window.print() asynchronously
    dlg = native.wait_dialog("print", timeout=web.long_timeout)
    assert any("Destination" in t or "Printer" in t for t in dlg.texts()), dlg.texts()
    dlg.click_any("Cancel")
    dlg.wait_closed()
