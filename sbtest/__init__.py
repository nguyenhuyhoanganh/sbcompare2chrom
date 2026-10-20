"""sbtest - automation base for Samsung Internet (Chromium fork) on Windows.

Layers:
    sbtest.browser  launch/attach the browser, profiles, chromedriver resolution
    sbtest.core     web layer (Selenium): locators, waits, actions, reading, tabs, JS dialogs
    sbtest.native   native layer (pywinauto/UIA): browser chrome UI, OS dialogs, bubbles, keys
    sbtest.pages    page objects for internal pages (bookmarks, history, downloads, ...)
    sbtest.data     test data: builders, seeders, generated files
    sbtest.server   local HTTP site used as deterministic test content
    sbtest.tools    exploration CLIs for test authors (inspect DOM, dump UIA, coverage)
"""
__version__ = "0.1.0"
