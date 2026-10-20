"""Reference: prompts drawn by the browser - HTTP sign-in, permission prompts."""
import pytest

from sbtest.steps import step

pytestmark = pytest.mark.native


def test_http_basic_auth_dialog(web, native, site):
    web.open(site.url("/index.html"))
    with step("navigate to a page that requires sign-in", expected="Sign in dialog"):
        web.open(site.url("/basic-auth"), blocking=False)   # don't wait for a load behind the prompt
        dlg = native.wait_dialog("http_auth")
    with step("fill user/password, Sign in", expected="page loads"):
        dlg.set_text("sbtest", title_re="(?i)user")
        dlg.set_text("sbtest", title_re="(?i)pass")
        dlg.click("Sign in")
        web.wait_title("Signed in")


def test_notification_permission_allow(web, native, site):
    web.open(site.url("/permissions.html"))
    web.click("#notify")
    prompt = native.wait_dialog("permission_prompt")
    prompt.click_any("Allow while visiting", "Allow")
    web.wait_text("#notify-state", "granted")


def test_location_permission_block(web, native, site):
    web.open(site.url("/permissions.html"))
    web.click("#geo")
    prompt = native.wait_dialog("permission_prompt")
    prompt.click_any("Never allow", "Block", "Don't allow")
    web.wait_text("#geo-state", "denied")
