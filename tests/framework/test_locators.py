from selenium.webdriver.common.by import By

from sbtest.web.locators import Locator, parse


def test_default_is_css():
    assert parse("#a .b") == Locator("css", "#a .b")


def test_prefixes():
    assert parse("xpath=//a").kind == "xpath"
    assert parse("//a").kind == "xpath"
    assert parse("(//a)[1]").kind == "xpath"
    assert parse("id=x") == Locator("id", "x")
    assert parse("text=Delete") == Locator("text", "Delete")
    assert parse("text~=del") == Locator("textc", "del")
    assert parse("aria=Search") == Locator("aria", "Search")
    assert parse("deepcss=cr-toast") == Locator("deepcss", "cr-toast")


def test_shadow_path():
    assert parse("a-app >>> #x >>> input") == Locator("deep", ("a-app", "#x", "input"))
    assert parse("deep=#only") == Locator("deep", ("#only",))
    assert parse("css=a >>> b").kind == "deep"


def test_tuple():
    assert parse((By.ID, "x")) == Locator("id", "x")
    assert parse((By.CSS_SELECTOR, "a")) == Locator("css", "a")
