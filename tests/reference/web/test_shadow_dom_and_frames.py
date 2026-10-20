"""Reference: locators through shadow roots (all internal pages use them) and iframes."""


def test_shadow_dom_locators(web, site):
    web.open(site.url("/shadow.html"))
    assert web.text("my-app >>> #hdr") == "Header text"           # shadow path
    assert web.count("my-app >>> my-card") == 2
    second = web.find_all("my-app >>> my-card")[1]
    web.click(web.find("deep=#action", within=second))            # inside one host's shadow root
    assert web.attr("my-app >>> my-card:nth-of-type(2)", "clicked") == "yes"
    web.type("aria=Card field", "typed")                          # by aria-label/placeholder
    assert web.value("my-app >>> my-card >>> #field") == "typed"
    assert web.exists("text=Second card")                         # by visible text
    assert web.count("deepcss=button") == 2                       # CSS in every shadow root
    assert "Header text" in web.page_text()


def test_iframe(web, site):
    web.open(site.url("/frames.html"))
    with web.frame("#inner"):
        assert web.text("#inner-title") == "Inside the frame"
        web.type("#inner-input", "hello parent")
        web.click("#inner-send")
    web.wait_text("#from-frame", "hello parent")
    assert web.text("#title") == "Frames"
