"""Reference: JavaScript alert / confirm / prompt / leave-site (beforeunload) and <dialog>."""
from sbtest.steps import step


def test_alert_confirm_prompt(web, site):
    web.open(site.url("/dialogs.html"))
    with step("alert"):
        web.click("#alert")
        assert web.accept_alert() == "Hello alert"
    with step("confirm accept / dismiss"):
        web.click("#confirm")
        web.accept_alert()
        web.wait_text("#result", "confirmed")
        web.click("#confirm")
        web.dismiss_alert()
        web.wait_text("#result", "cancelled")
    with step("prompt with text"):
        web.click("#prompt")
        web.accept_alert(prompt_text="Samsung")
        web.wait_text("#result", "prompt:Samsung")


def test_leave_site_prompt_is_auto_accepted(web, site):
    """WebDriver (chromedriver) accepts "Leave site?" (beforeunload) prompts by itself, per the
    WebDriver spec - they never reach the test, and the navigation simply happens. A case that
    must check the prompt's own UI is not automatable with this stack (mark it in the doc)."""
    web.open(site.url("/dialogs.html"))
    web.click("#arm-beforeunload")
    web.wait_text("#result", "armed")
    web.open(site.page("Elsewhere"))
    web.wait_title("Elsewhere")
    assert not web.has_alert()


def test_html_dialog_element(web, site):
    """<dialog> is plain DOM - no alert handling needed."""
    web.open(site.url("/dialogs.html"))
    web.click("#html-dialog")
    web.wait_visible("#dlg")
    web.click("#dlg-close")
    web.wait_gone("#dlg")
