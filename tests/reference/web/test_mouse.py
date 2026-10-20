"""Reference: click, double click, right click (web menu), hover, scrolling, mouse drag."""


def test_click_double_right_hover(web, site):
    web.open(site.url("/mouse.html"))
    web.click("#click-me")
    web.wait_text("#result", "clicked", contains=False)
    web.double_click("#dbl")
    web.wait_text("#result", "double clicked")
    web.right_click("#ctx")                      # page's own context menu (DOM)
    web.click("#ctx-copy")
    web.wait_text("#result", "menu: copy")
    web.hover("#hover-menu")                     # CSS :hover reveals the sub menu
    web.click("#sub-item")
    web.wait_text("#result", "sub item")


def test_scroll_to_far_element(web, site):
    web.open(site.url("/mouse.html"))
    assert web.js("return window.scrollY") == 0
    web.click("#far")                            # click scrolls the element into view itself
    web.wait_text("#result", "far clicked")
    assert web.js("return window.scrollY") > 0
    web.scroll_by(0, -5000)
    assert web.js("return window.scrollY") == 0


def test_mouse_drag_by_offset(web, site):
    web.open(site.url("/dragdrop.html"))
    web.drag_by("#mouse-drag", 150, 40)
    web.wait_text("#mouse-result", "moved:")
