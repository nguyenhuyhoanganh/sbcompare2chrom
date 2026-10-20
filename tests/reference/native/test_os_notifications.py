"""Reference: Windows toast shown by a web notification (permission granted up front).
Focus Assist / Do Not Disturb hides toasts - turn it off on the test machine."""
import pytest

pytestmark = [pytest.mark.native,
              pytest.mark.browser(prefs={"profile.default_content_setting_values.notifications": 1})]


def test_web_notification_shows_windows_toast(web, native, site):
    web.open(site.url("/permissions.html"))
    web.click("#notify")
    web.wait_text("#notify-state", "granted")
    native.wait_os_toast("(?i)sbtest notification", timeout=15)
