"""sbtest - automation base for Samsung Internet for Windows (Chromium fork).

    sbtest.config      layered configuration, targets (samsung | chrome)
    sbtest.browser     launch/attach the browser, profiles, Chromium version, chromedriver
    sbtest.web         web layer (Selenium): locators, waits, actions, reading, tabs, frames, JS dialogs
    sbtest.native      native layer (pywinauto/UIA): browser UI, prompts, Windows dialogs, Explorer, keys
    sbtest.pages       page objects: chromium/ (reference) and samsung/ (product)
    sbtest.data        test data: builders, loaders, generated files
    sbtest.server      local HTTP site used as deterministic test content
    sbtest.reporting   failure evidence, results.json, Confluence export
    sbtest.tools       CLIs: doctor, dom, uia_dump, coverage, get_chrome, confluence_export
"""
__version__ = "0.2.0"
