"""Samsung bookmark manager (internet://bookmarks; WebDriver URL chrome://bookmarks).

STATUS: verified on Samsung Browser 31.0.0.55 (Chromium 148).

How it differs from Chromium:
- rows are selected with a round check box (si-select); Edit / Share / Delete / Select all
  live in the page toolbar and act on the selection (no ⋮ per row)
- right click on a row opens a menu: Edit, Delete, Open all (n) in new tab / window / Secret mode
- right ⋮ (toolbar): Add bookmark (same dialog as Edit), Sort by name, Open all (n) in new
  tabs / new window / Secret mode
- "Create folder" adds "Folder 1" in the selected folder, opens it and puts its name in edit
  mode in the left tree (type the name + Enter)
- Delete removes at once and shows a snack bar "1 bookmark deleted" with Undo
- left ⋮ (Options): Create folder in selected folder, Sort by name, Import bookmarks (opens
  Settings in a new tab), Export bookmarks (Windows Save As, HTML)
- Sort by name puts folders first, then bookmarks A-Z
- root folders: "PC bookmarks" > "Bookmark bar"
"""
from __future__ import annotations

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.action_chains import ActionChains

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
    BAR_FOLDER = "Bookmark bar"

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

    # -- reading -----------------------------------------------------------------
    def item_url(self, title: str) -> str:
        return self.web.text(self.web.find("deep=si-searched-label.url", within=self.item(title)))

    def folders(self) -> list[str]:
        """Folder names of the left tree (root folders included)."""
        return [self.web.attr(e, "aria-label") for e in self.web.find_all(self.TREE_ITEM)]

    # -- navigation --------------------------------------------------------------
    def expand_tree(self) -> None:
        """The Samsung tree renders expanded; nothing to do."""

    def open_folder(self, name: str) -> None:
        self.web.click(f"deepcss=#container[role=treeitem][aria-label={q(name)}]")
        self.web.wait_until(lambda: self.selected_folder() == name, message=f"folder {name} selected")

    def open_item(self, title: str) -> None:
        """Click the row: opens a folder in the list, or the bookmarked page in a NEW TAB
        (switched to)."""
        before = self.web.tabs
        is_folder = bool(self.web.find_all("deep=#folderIcon", within=self.item(title)))
        self.web.click(self.web.find("deep=#website-title", within=self.item(title)))
        if not is_folder:
            self.web.wait_new_tab(before)

    def organize(self, action: str) -> None:
        """Left ⋮ menu: ``Create folder in selected folder`` | ``Sort by name`` |
        ``Import bookmarks`` | ``Export bookmarks``."""
        self.web.click(self.OPTIONS_MENU)
        self.click_menu_item(action)

    # -- edit dialog ---------------------------------------------------------------
    def _fill_edit_dialog(self, name: str | None, url: str | None) -> None:
        if name is not None:
            self.web.type(f"{self.EDIT_DIALOG} >>> #name >>> #input", name)
        if url is not None:
            self.web.type(f"{self.EDIT_DIALOG} >>> #url >>> #input", url)

    def save_dialog(self) -> None:
        save = f"{self.EDIT_DIALOG} >>> #saveButton >>> #siDialogButton"
        self.web.wait_until(lambda: self.web.is_enabled(save), message="Save enabled (a field changed)")
        self.web.click(save)
        self.wait_dialog_closed()

    def add_bookmark(self, name: str, url: str) -> None:
        """Right ⋮ > Add bookmark -> Name + Web address -> Save (into the open folder)."""
        self.options("Add bookmark")
        self.open_dialog()
        self._fill_edit_dialog(name, url)
        self.save_dialog()
        self.wait_item(name)

    # -- add -----------------------------------------------------------------------
    def add_folder(self, name: str) -> None:
        """Toolbar "Create folder" in the current folder, type the name in the tree, Enter.
        Goes back to the parent folder so the new folder shows in ``titles()``."""
        parent = self.selected_folder()
        before = set(self.folders())
        self.toolbar("Create folder")
        new = self.web.wait_until(lambda: next((f for f in self.folders() if f not in before), None),
                                  message="new folder in tree")
        # the new name field is focused with "Folder N" selected (it is readonly to clicks):
        # type over it with the keyboard
        self.web.wait_until(lambda: self.web.js(
            "let a = document.activeElement; while (a && a.shadowRoot && a.shadowRoot.activeElement)"
            " a = a.shadowRoot.activeElement; return a && a.id === 'input' && a.getAttribute('aria-label') === arguments[0]",
            new), message=f"{new!r} name field focused")
        ActionChains(self.web.driver).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL) \
            .send_keys(name).send_keys(Keys.ENTER).perform()
        self.web.wait_until(lambda: name in self.folders(), message=f"folder {name!r} in tree")
        if parent:
            self.open_folder(parent)
        self.wait_item(name)

    # -- row context menu ------------------------------------------------------------
    def item_menu(self, title: str, action: str) -> None:
        """Right click a row: ``Edit`` | ``Delete`` | ``Open all (1) in new tab`` | ``... new window``
        | ``... Secret mode``. ``action`` may be a prefix (``Open all``...)."""
        ActionChains(self.web.driver).context_click(self.web.find("deep=#website-title", within=self.item(title))).perform()
        items = self.web.wait_until(lambda: self.menu_items() or None, message="bookmark context menu")
        match = next((i for i in items if i == action), None) or next((i for i in items if i.startswith(action)), None)
        if match is None:
            raise LookupError(f"{action!r} not in context menu {items}")
        self.click_menu_item(match)

    def edit(self, title: str, name: str | None = None, url: str | None = None) -> None:
        """Select the row -> toolbar Edit -> change name / URL -> Save."""
        self.select(title)
        self.toolbar("Edit")
        self.open_dialog()
        self._fill_edit_dialog(name, url)
        self.save_dialog()
        if name is not None:
            self.wait_item(name)

    def delete(self, title: str) -> str:
        """Select + toolbar Delete; returns the snack bar text ("1 bookmark deleted")."""
        self.select(title)
        toast = self.delete_selected()
        self.wait_item(title, present=False)
        return toast

    # -- selection + toolbar -----------------------------------------------------------
    def select(self, *titles: str) -> None:
        """Tick the round check box of each row (multi-select needs no Ctrl)."""
        for t in titles:
            if not self.is_selected(t):
                self.web.click(self.web.find("deep=#checkbox", within=self.item(t)))
        self.web.wait_until(lambda: all(self.is_selected(t) for t in titles), message=f"{titles} selected")

    def delete_selected(self) -> str:
        """Toolbar Delete ("Delete all" when every row is selected); returns the snack bar text."""
        self.toolbar_any("Delete", "Delete all")
        return self.wait_toast("deleted")

    def undo(self) -> None:
        self.web.click(self.UNDO)

    OPTIONS_MENU = "bookmarks-app >>> bookmarks-toolbar >>> si-toolbar.bookmarks-toolbar >>> #moreMenuButton"
    RIGHT_MENU = "bookmarks-app >>> bookmarks-toolbar >>> #menuButton"
    TREE_ITEM = "deepcss=#container[role=treeitem]"
    UNDO = "bookmarks-app >>> #undoButton"
    ROOT_FOLDERS = ("PC bookmarks", "Bookmark bar")

    def selected_folder(self) -> str:
        sel = [self.web.attr(e, "aria-label") for e in self.web.find_all(self.TREE_ITEM)
               if "selected" in (self.web.attr(e, "class") or "")]
        return sel[0] if sel else ""

    def is_selected(self, title: str) -> bool:
        return self.web.is_checked(self.web.find("deep=#checkbox", within=self.item(title)))

    def options(self, action: str) -> None:
        """Right ⋮ menu of the list: ``Add bookmark`` | ``Sort by name`` | ``Open all (n) in new
        tabs`` / ``... new window`` / ``... Secret mode`` (prefix match)."""
        self.web.click(self.RIGHT_MENU)
        items = self.web.wait_until(lambda: self.menu_items() or None, message="options menu")
        match = next((i for i in items if i == action), None) or next((i for i in items if i.startswith(action)), None)
        if match is None:
            raise LookupError(f"{action!r} not in options menu {items}")
        self.click_menu_item(match)

    def export(self, native, path) -> None:
        """Left ⋮ > Export bookmarks -> Windows Save As (HTML file)."""
        self.organize("Export bookmarks")
        native.file_dialog("save").save_as(path)
