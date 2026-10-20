"""Bookmark manager (chrome://bookmarks)."""
from __future__ import annotations

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.base import BasePage, q


class BookmarksPage(BasePage):
    page = "bookmarks"
    ROOT = "bookmarks-app >>> bookmarks-list"
    TOOLBAR_MENU = "bookmarks-app >>> bookmarks-toolbar >>> #menuButton"        # "Organize" (⋮)
    TOOLBAR = "bookmarks-app >>> bookmarks-toolbar"
    ITEMS = "bookmarks-app >>> bookmarks-list >>> bookmarks-item"
    ITEM_TITLE = "bookmarks-app >>> bookmarks-list >>> bookmarks-item >>> #website-title"
    SIDEBAR_FOLDER = "deepcss=bookmarks-folder-node"
    EDIT_DIALOG = "bookmarks-app >>> bookmarks-command-manager >>> bookmarks-edit-dialog"
    #: name of the bookmarks bar folder in the tree
    BAR_FOLDER = "Bookmarks bar"

    # -- reading -----------------------------------------------------------------
    def titles(self) -> list[str]:
        """Titles shown in the list for the current folder / search, in order."""
        return [self.web.attr(el, "title") or self.web.text(el) for el in self.web.find_all(self.ITEM_TITLE)]

    def item(self, title: str, timeout: float | None = None) -> WebElement:
        return self.web.find(f"bookmarks-app >>> bookmarks-list >>> bookmarks-item[aria-label={q(title)}]", timeout)

    def has_item(self, title: str) -> bool:
        return title in self.titles()

    def wait_titles(self, expected: list[str], timeout: float | None = None) -> list[str]:
        return self.web.wait_until(lambda: self.titles() if self.titles() == expected else None,
                                   timeout, f"bookmark titles == {expected}")

    def wait_item(self, title: str, present: bool = True, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: self.has_item(title) == present, timeout,
                            f"bookmark {title!r} {'present' if present else 'absent'}")

    def item_url(self, title: str) -> str:
        """URL of an item (from the Edit dialog's model via the item's ``itemUrl_``/``item_``)."""
        el = self.item(title)
        return self.web.js("const e = arguments[0]; return (e.item_ && e.item_.url) || e.itemUrl_ || '';", el)

    def folders(self) -> list[str]:
        """All folder names in the left tree (expands it first)."""
        self.expand_tree()
        return [t for t in (self.web.attr(e, "title") for e in self.web.find_all("deepcss=.menu-label")) if t]

    # -- navigation --------------------------------------------------------------
    def expand_tree(self) -> None:
        """Expand every collapsed node of the folder tree."""
        for _ in range(20):
            collapsed = self.web.find_all('deepcss=#container[role=treeitem][aria-expanded="false"]')
            if not collapsed:
                return
            for c in collapsed:
                self.web.click(self.web.js("return arguments[0].parentNode.querySelector('#arrow')", c))

    def open_folder(self, name: str) -> None:
        """Select a folder in the left tree (``Bookmarks bar``, ``Other bookmarks``, or a sub folder)."""
        self.expand_tree()
        self.web.click(f"deepcss=.menu-label[title={q(name)}]")
        self.web.wait_until(lambda: self.web.exists(
            f"deepcss=.cr-nav-menu-item.selected .menu-label[title={q(name)}]"), message=f"folder {name} selected")

    def open_item(self, title: str) -> None:
        """Double click: opens a folder in the list, or the page for a URL item."""
        self.web.double_click(self.item(title))

    # -- organize menu (toolbar ⋮) ----------------------------------------------
    def organize(self, action: str) -> None:
        """``Add new bookmark`` | ``Add new folder`` | ``Sort by name`` | ``Import bookmarks`` | ``Export bookmarks``"""
        self.web.click(self.TOOLBAR_MENU)
        self.click_menu_item(action)

    def _fill_edit_dialog(self, name: str | None, url: str | None) -> None:
        if name is not None:
            self.web.type(f"{self.EDIT_DIALOG} >>> #name >>> input", name)
        if url is not None:
            self.web.type(f"{self.EDIT_DIALOG} >>> #url >>> input", url)

    def save_dialog(self) -> None:
        self.web.click(f"{self.EDIT_DIALOG} >>> #saveButton")
        self.wait_dialog_closed()

    def add_bookmark(self, name: str, url: str) -> None:
        self.organize("Add new bookmark")
        self._fill_edit_dialog(name, url)
        self.save_dialog()
        self.wait_item(name)

    def add_folder(self, name: str) -> None:
        self.organize("Add new folder")
        self._fill_edit_dialog(name, None)
        self.save_dialog()
        self.wait_item(name)

    # -- item menu (⋮ on a row) -------------------------------------------------
    def item_menu(self, title: str, action: str) -> None:
        """``Edit`` | ``Delete`` | ``Copy URL`` | ``Open in new tab`` | ``Open in new window`` | ``Show in folder`` ..."""
        self.web.click(self.web.find("deep=#menuButton", within=self.item(title)))
        self.click_menu_item(action)

    def edit(self, title: str, name: str | None = None, url: str | None = None) -> None:
        self.item_menu(title, "Edit")
        self._fill_edit_dialog(name, url)
        self.save_dialog()
        if name is not None:
            self.wait_item(name)

    def delete(self, title: str) -> str:
        """Delete through the item menu; returns the toast text (e.g. "'X' deleted")."""
        self.item_menu(title, "Delete")
        self.wait_item(title, present=False)
        return self.wait_toast()

    def select(self, *titles: str) -> None:
        """Select one or more rows (Ctrl+click for the extra ones)."""
        from selenium.webdriver.common.action_chains import ActionChains

        self.web.click(self.item(titles[0]))
        for t in titles[1:]:
            el = self.item(t)
            ActionChains(self.web.driver).key_down(Keys.CONTROL).click(el).key_up(Keys.CONTROL).perform()

    def delete_selected(self) -> str:
        """Toolbar "Delete" shown while rows are selected (or the Delete key)."""
        self.click_text("Delete", css="cr-button", within=self.web.find(self.TOOLBAR))
        return self.wait_toast()

    def undo(self) -> None:
        self.toast_action("Undo")
