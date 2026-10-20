"""Reference: print preview dialog opened by window.print().

While print preview is open the page is blocked: do NOT call web.* until it is closed.
Its controls (Destination, Print, Cancel) are web content that UIA exposes lazily, so close
it with Esc instead of looking for the Cancel button.
"""
import pytest

pytestmark = pytest.mark.native


def test_print_dialog_open_and_cancel(web, native, site):
    web.open(site.url("/dialogs.html"))
    web.click("#print")                           # the page calls window.print() asynchronously
    dlg = native.wait_dialog("print", timeout=web.long_timeout)   # Pane "Print"
    dlg.press("{ESC}")
    dlg.wait_closed()
    assert web.title == "Dialogs page"            # page answers again once the preview is gone
