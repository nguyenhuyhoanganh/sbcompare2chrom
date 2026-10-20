"""Reference: navigation, redirects, status pages, tabs and popup windows (web layer)."""
from sbtest.steps import step


def test_open_back_forward_refresh(web, site):
    web.open(site.url("/pages/page1.html"))
    web.click("#next")
    web.wait_title("Static page 2")
    web.back()
    web.wait_title("Static page 1")
    web.forward()
    web.wait_title("Static page 2")
    web.refresh()
    web.wait_title("Static page 2")


def test_redirect_and_status_page(web, site):
    web.open(site.url("/redirect", to="/page?title=Landed"))
    web.wait_title("Landed")
    assert "/page?title=Landed" in web.url
    web.open(site.url("/status", code=404))
    assert web.text("h1") == "Status 404"


def test_internal_page_of_target(web, cfg):
    """Internal pages are opened by logical name; the scheme comes from the target config."""
    web.open_internal("version")
    assert web.url.startswith(cfg.page_url("version"))


def test_link_opens_new_tab_and_switch_back(web, site):
    web.open(site.url("/popups.html"))
    first = web.driver.current_window_handle
    before = web.tabs
    with step("click target=_blank link", expected="new tab with page 2"):
        web.click("#blank-link")
        web.wait_new_tab(before)          # switches to the new tab
        web.wait_title("Static page 2")
    web.switch_tab(title="Popups page")
    assert web.driver.current_window_handle == first


def test_window_open_popup(web, site):
    web.open(site.url("/popups.html"))
    before = web.tabs
    web.click("#window-open")
    web.wait_new_tab(before)
    web.wait_title("Static page 3")
    web.close_tab()                       # back to the opener
    assert web.title == "Popups page"


def test_new_tab_by_api(web, site):
    web.new_tab(site.page("Second tab"))
    assert web.title == "Second tab"
    web.switch_tab(index=0)
