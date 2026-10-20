"""Wrappers for native dialogs: generic browser prompts/bubbles and Windows common dialogs.

    dlg = native.wait_dialog("add_extension")      # logical name from config/native_ui/<target>.yaml
    assert "Read and change" in " ".join(dlg.texts())
    dlg.click("Add extension")

    fd = native.file_dialog("save")                # Save As / Open common dialog
    fd.save_as(tmp_path / "page.html")
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from sbtest.native import uia
from sbtest.utils import log, poll


class Dialog:
    """A native window/pane: read texts, click buttons, toggle checkboxes, fill edits."""

    def __init__(self, element, timeout: float = 10) -> None:
        self.el = element
        self.timeout = timeout

    @property
    def title(self) -> str:
        return self.el.element_info.name or ""

    def texts(self) -> list[str]:
        return uia.texts(self.el)

    def text(self) -> str:
        return "\n".join(self.texts())

    def find(self, timeout: float | None = None, **criteria):
        return uia.find_in([self.el], self.timeout if timeout is None else timeout, **criteria)

    def button(self, name: str, exact: bool = False):
        crit = {"title": name} if exact else {"title_re": f"(?i){re.escape(name)}"}
        return self.find(control_type="Button", **crit)

    def click(self, name: str, exact: bool = False, real_mouse: bool = False) -> None:
        """Click a button by (partial, case-insensitive) name."""
        b = self.button(name, exact)
        if real_mouse or b.element_info.class_name != "Button":
            # browser (Views) bubbles fade in and ignore UIA Invoke until they are fully shown,
            # so wait for the animation and use the real mouse; Win32 buttons ("Button") invoke fine
            if not real_mouse:
                time.sleep(0.5)
            b.click_input()
        else:
            try:
                b.invoke()
            except Exception:  # noqa: BLE001 - some Views buttons only react to real input
                b.click_input()

    def click_any(self, *names: str) -> str:
        """Click the first button whose name matches one of ``names`` (labels change between
        versions, e.g. "Allow" / "Allow while visiting the site"). Returns the label used."""
        for name in names:
            b = uia.find_in([self.el], 0, control_type="Button", title_re=f"(?i){re.escape(name)}")
            if b is not None:
                if b.element_info.class_name != "Button":  # Views bubble: see click()
                    time.sleep(0.5)
                    b.click_input()
                else:
                    try:
                        b.invoke()
                    except Exception:  # noqa: BLE001
                        b.click_input()
                return b.element_info.name
        raise LookupError(f"none of the buttons {names} in dialog {self.title!r}: {self.texts()}")

    def set_checkbox(self, name: str, checked: bool = True) -> None:
        cb = self.find(control_type="CheckBox", title_re=f"(?i){re.escape(name)}")
        if bool(cb.get_toggle_state()) != checked:
            cb.toggle()

    def set_text(self, value: str, **criteria) -> None:
        crit = {"control_type": "Edit", **criteria}
        edit = self.find(**crit)
        try:
            edit.set_edit_text(value)
        except Exception:  # noqa: BLE001 - UIA ValuePattern not always available
            edit.click_input()
            edit.type_keys("^a{BACKSPACE}" + _escape_keys(value), with_spaces=True)

    def press(self, keys: str) -> None:
        """pywinauto key syntax: ``{ENTER}``, ``{ESC}``, ``^a`` ..."""
        self.el.set_focus()
        self.el.type_keys(keys, with_spaces=True)

    def close(self) -> None:
        try:
            self.el.close()
        except Exception:  # noqa: BLE001
            self.press("{ESC}")

    def is_open(self) -> bool:
        # A stale UIA element can keep reporting is_visible() after its window is destroyed,
        # so check the HWND when there is one (common dialogs, top-level windows).
        try:
            handle = self.el.element_info.handle
            if handle:
                from pywinauto import handleprops
                return bool(handleprops.iswindow(handle) and handleprops.isvisible(handle))
            return self.el.is_visible()
        except Exception:  # noqa: BLE001 - element gone
            return False

    def wait_closed(self, timeout: float | None = None) -> None:
        poll(lambda: not self.is_open(), self.timeout if timeout is None else timeout, 0.3, f"dialog closed {self.title!r}")

    def dump(self) -> str:
        return uia.dump(self.el)


class FileDialog(Dialog):
    """Windows common Open / Save As / Select Folder dialog (#32770)."""

    # ComboBox 1148 (Open) / Edit 1001 (Save As) / Edit 1152 "Folder:" (Select Folder). The ids
    # are reused by other controls (Windows 11 has a ToolBar with id 1001 in the Open dialog),
    # so match the type too.
    FILENAME_IDS = (("1148", "ComboBox"), ("1001", "Edit"), ("1152", "Edit"))

    def _filename_edit(self):
        for aid, ctype in self.FILENAME_IDS:
            el = uia.find_in([self.el], 0, auto_id=aid, control_type=ctype)
            if el is not None:
                if ctype == "ComboBox":
                    el = uia.find_in([el], 0, control_type="Edit") or el
                return el
        return self.find(control_type="Edit", title_re="(?i)file name")

    def set_filename(self, path: str | Path) -> None:
        # Real keystrokes: the Save As dialog ignores text set through the UIA ValuePattern
        # (the edit shows it, but Save keeps the suggested name or does nothing).
        # Keystrokes are occasionally dropped while the path autocomplete pops up: check the
        # field and type again, slower, when it does not hold the full path.
        edit = self._filename_edit()
        for pause in (0.01, 0.04, 0.08):
            edit.set_focus()
            edit.type_keys("^a{BACKSPACE}" + _escape_keys(str(path)), with_spaces=True, pause=pause)
            try:
                poll(lambda: _value(edit) == str(path), 2, 0.2, f"file name typed {str(path)!r}")
                return
            except TimeoutError:
                log.warning("file name field holds %r, typing %r again", _value(edit), str(path))
        raise TimeoutError(f"file name field holds {_value(edit)!r} instead of {str(path)!r}")

    def _confirm(self, *labels: str) -> None:
        btn = uia.find_in([self.el], 0, auto_id="1", control_type="Button")
        if btn is None:
            for label in labels:
                btn = uia.find_in([self.el], 0, control_type="Button", title_re=f"(?i)^{label}")
                if btn is not None:
                    break
        if btn is None:
            self.press("{ENTER}")
        else:
            btn.click_input()

    def save_as(self, path: str | Path, overwrite: bool = True) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.set_filename(path)
        self._confirm("save")
        time.sleep(0.5)
        confirm = uia.find_in(lambda: [self.el], 0, control_type="Button", title_re="(?i)^yes$")
        if confirm is not None:  # "already exists. Replace?"
            (confirm if overwrite else uia.find_in([self.el], 0, control_type="Button", title_re="(?i)^no$")).click_input()
        return path

    def open(self, *paths: str | Path) -> None:
        """Choose one or more files (multi-select uses quoted names in the same folder)."""
        if len(paths) == 1:
            self.set_filename(Path(paths[0]).resolve())
        else:
            folder = Path(paths[0]).resolve().parent
            self.set_filename(folder)
            self.press("{ENTER}")
            time.sleep(0.5)
            self.set_filename(" ".join(f'"{Path(p).name}"' for p in paths))
        self._confirm("open")

    def select_folder(self, folder: str | Path) -> None:
        """Folder picker: Enter on the typed path opens that folder, then "Select Folder" with an
        empty field picks the open folder (clicking it straight after typing is swallowed by
        the path autocomplete drop-down)."""
        self.set_filename(Path(folder).resolve())
        self._filename_edit().type_keys("{ENTER}")
        time.sleep(0.8)
        edit = self._filename_edit()
        edit.set_focus()
        edit.type_keys("^a{BACKSPACE}")
        self._confirm("select folder", "ok")

    def cancel(self) -> None:
        btn = uia.find_in([self.el], 0, auto_id="2", control_type="Button")
        if btn is not None:
            btn.click_input()
        else:
            self.press("{ESC}")


def _value(edit) -> str:
    try:
        return edit.get_value() or ""
    except Exception:  # noqa: BLE001
        return edit.window_text() or ""


def _escape_keys(text: str) -> str:
    """Escape pywinauto send_keys special characters."""
    return re.sub(r"([{}+^%~()\[\]])", r"{\1}", text)
