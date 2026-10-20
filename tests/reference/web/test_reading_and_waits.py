"""Reference: reading content and waiting for it - text, lists, attributes, state, late
content, in-page toasts, whole page text."""


def test_read_text_attributes_state(web, site):
    web.open(site.url("/form.html"))
    assert web.text("h1") == "Form"
    assert web.attr("#form", "action").endswith("/upload")
    assert web.count("#form input[type=radio]") == 2
    assert web.exists("#submit") and not web.exists("#does-not-exist")
    assert not web.is_checked("#agree")
    web.click("#agree")
    assert web.is_checked("#agree")
    assert "Agree" in web.page_text()


def test_texts_of_list(web, site):
    web.open(site.url("/index.html"))
    links = web.texts("#links a")
    assert links[0] == "Form" and "Mouse" in links


def test_wait_for_late_content(web, site):
    web.open(site.url("/delayed", ms=1200, text="Loaded later"))
    assert not web.exists("#late")
    web.wait_text("#late", "Loaded later")


def test_in_page_toast_appears_and_disappears(web, site):
    web.open(site.url("/toast.html"))
    web.click("#show-toast")
    web.wait_text("#toast", "Saved successfully")
    web.wait_gone("#toast", timeout=6)
