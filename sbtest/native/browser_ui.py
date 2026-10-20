"""NativeBrowser: the browser's own UI and its dialogs through UI Automation.

    nb = session.native
    nb.hotkey("^d")                          # Ctrl+D -> bookmark bubble
    bubble = nb.wait_dialog("bookmark_added")
    bubble.click("Done")
    nb.click("bookmark_star")                # logical name from config/native_ui.yaml
    nb.menu("History", "History")            # app menu path
    nb.context_menu_web(web, "#link", "Open link in new tab")
    nb.file_dialog("save").save_as(path)
    nb.wait_text(r"Bookmark added")          # any element in any browser window
    nb.dump("artifacts/uia.txt")             # discover names/criteria

Key syntax (pywinauto): ``^`` Ctrl, ``+`` Shift, ``%`` Alt, ``{ENTER}`` ``{ESC}`` ``{TAB}``
``{F5}`` ``{DELETE}`` ``{DOWN}``; ``"^+{DELETE}"`` = Ctrl+Shift+Delete.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import yaml

from sbtest.config import Config
from sbtest.native import require, uia
from sbtest.native.dialogs import Dialog, FileDialog
from sbtest.utils import log, poll


class NativeBrowser:
    def __init__(self, pid: int, cfg: Config) -> None:
        require()
        from pywinauto import Desktop

        self.pid = pid
        self.cfg = cfg
        self.timeout = float(cfg.get("timeouts.native", 10))
        self.desktop = Desktop(backend=cfg.get("native.backend", "uia"))
        self.ui_map: dict = yaml.safe_load(cfg.path("native.ui_map").read_text(encoding="utf-8")) or {}

    # -- windows -----------------------------------------------------------------
    def pids(self) -> set[int]:
        """Browser process + its children (some dialogs are owned by utility processes)."""
        import psutil

        try:
            return {self.pid} | {p.pid for p in psutil.Process(self.pid).children(recursive=True)}
        except psutil.Error:
            return {self.pid}

    def windows(self, visible_only: bool = True) -> list:
        """All top-level windows of the browser (main windows, bubbles, menus, dialogs)."""
        pids = self.pids()
        try:
            wins = self.desktop.windows(visible_only=visible_only)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for w in wins:
            try:
                if w.element_info.process_id in pids:
                    out.append(w)
            except Exception:  # noqa: BLE001 - window vanished
                pass
        return out

    def main_window(self):
        def _main():
            wins = [w for w in self.windows() if w.element_info.class_name == "Chrome_WidgetWin_1"
                    and w.element_info.control_type in ("Window", "Pane")]
            # the browser frame is the biggest one
            wins.sort(key=lambda w: w.rectangle().width() * w.rectangle().height(), reverse=True)
            return wins[0] if wins else None
        return poll(_main, self.timeout, 0.3, f"main browser window of pid {self.pid}")

    def focus(self) -> None:
        w = self.main_window()
        try:
            w.set_focus()
        except Exception as e:  # noqa: BLE001
            log.debug("set_focus failed: %s", e)

    # -- keyboard ----------------------------------------------------------------
    def hotkey(self, keys: str, focus: bool = True) -> None:
        """Browser-level shortcut, e.g. ``"^d"`` bookmark, ``"^h"`` history, ``"^j"`` downloads,
        ``"^t"`` new tab, ``"^+{DELETE}"`` clear browsing data, ``"{F11}"`` fullscreen."""
        from pywinauto import keyboard

        if focus:
            self.focus()
        keyboard.send_keys(keys, pause=0.05)

    def type_text(self, text: str) -> None:
        """Type literal text into whatever has focus (escapes pywinauto special chars)."""
        from pywinauto import keyboard

        from sbtest.native.dialogs import _escape_keys

        keyboard.send_keys(_escape_keys(text), with_spaces=True, pause=0.02)

    # -- elements by logical name ----------------------------------------------
    def criteria(self, name_or_criteria) -> dict:
        if isinstance(name_or_criteria, dict):
            return dict(name_or_criteria)
        if name_or_criteria not in self.ui_map:
            raise KeyError(f"{name_or_criteria!r} not in {self.cfg.get('native.ui_map')}")
        return dict(self.ui_map[name_or_criteria])

    def element(self, name_or_criteria, timeout: float | None = None, in_main: bool = True):
        """Element of the browser UI by logical name (native_ui.yaml) or criteria dict."""
        crit = self.criteria(name_or_criteria)
        roots = (lambda: [self.main_window()]) if in_main else self.windows
        return uia.find_in(roots, self.timeout if timeout is None else timeout, **crit)

    def exists(self, name_or_criteria, in_main: bool = True) -> bool:
        crit = self.criteria(name_or_criteria)
        roots = [self.main_window()] if in_main else self.windows()
        return uia.find_in(roots, 0, **crit) is not None

    def click(self, name_or_criteria, real_mouse: bool = True, timeout: float | None = None) -> None:
        el = self.element(name_or_criteria, timeout)
        if real_mouse:
            el.click_input()
        else:
            el.invoke()

    # -- omnibox / tabs ----------------------------------------------------------
    def omnibox_text(self) -> str:
        el = self.element("omnibox")
        try:
            return el.get_value()
        except Exception:  # noqa: BLE001
            return el.window_text()

    def navigate(self, url: str) -> None:
        """Type a URL into the omnibox like a user (Ctrl+L, text, Enter)."""
        self.hotkey("^l")
        time.sleep(0.2)
        self.type_text(url)
        self.hotkey("{ENTER}", focus=False)

    def tab_titles(self) -> list[str]:
        strip = self.element("tab_strip")
        return [t.element_info.name for t in uia.descendants(strip, control_type="TabItem")]

    # -- menus -------------------------------------------------------------------
    def select_menu_items(self, *path: str, timeout: float | None = None) -> None:
        """Click through an *already open* native menu by item names (regex, case-insensitive)."""
        for item in path:
            mi = uia.find_in(self.windows, self.timeout if timeout is None else timeout,
                             control_type="MenuItem", title_re=f"(?i)^{item}")
            mi.click_input()
            time.sleep(0.3)

    def menu(self, *path: str) -> None:
        """App menu (the "..." / hamburger button) then items, e.g. ``menu("Bookmarks", "Bookmark manager")``."""
        self.click("app_menu_button")
        self.select_menu_items(*path)

    def context_menu_web(self, web, loc, *path: str) -> None:
        """Right-click a web element with the real mouse and pick native context menu items."""
        from pywinauto import mouse

        x, y = self.web_point(web, web.find(loc))
        mouse.right_click(coords=(x, y))
        if path:
            self.select_menu_items(*path)

    def menu_items(self) -> list[str]:
        """Names of items of the currently open native menu(s)."""
        out = []
        for w in self.windows():
            out += [e.element_info.name for e in uia.descendants(w, control_type="MenuItem")]
        return out

    # -- dialogs / bubbles -------------------------------------------------------
    def wait_dialog(self, name_or_regex: str, timeout: float | None = None) -> Dialog:
        """A dialog/bubble/prompt by logical name (``native_ui.yaml: dialogs``) or title regex.

        Searches top-level windows of the process first, then panes/dialogs inside them
        (Views bubbles are often child panes of the frame)."""
        pattern = (self.ui_map.get("dialogs") or {}).get(name_or_regex, name_or_regex)
        rx = re.compile(pattern)

        def _find():
            wins = self.windows()
            for w in wins:
                if rx.search(w.element_info.name or ""):
                    return w
            for w in wins:
                for ct in ("Dialog", "Window", "Pane", "Group"):
                    hits = uia.descendants(w, control_type=ct, title_re=pattern)
                    if hits:
                        return hits[0]
            return None

        el = poll(_find, self.timeout if timeout is None else timeout, 0.3, f"native dialog /{pattern}/")
        return Dialog(el, self.timeout)

    def file_dialog(self, kind: str = "save", timeout: float | None = None) -> FileDialog:
        """Windows Save As / Open / folder picker opened by the browser."""
        key = {"save": "file_save", "open": "file_open"}.get(kind, kind)
        pattern = (self.ui_map.get("dialogs") or {}).get(key, kind)

        def _find():
            for w in self.windows():
                if w.element_info.class_name == "#32770" or re.search(pattern, w.element_info.name or ""):
                    return w
                for d in uia.descendants(w, class_name="#32770"):
                    return d
            return None

        el = poll(_find, self.timeout if timeout is None else timeout, 0.3, f"file dialog {kind}")
        return FileDialog(el, self.timeout)

    def wait_text(self, pattern: str, timeout: float | None = None, control_type: str | None = None):
        """Wait until any element in any browser window has a name matching ``pattern``
        (bubble text, infobar, native toast inside the frame, permission prompt...)."""
        crit = {"title_re": pattern}
        if control_type:
            crit["control_type"] = control_type
        return uia.find_in(self.windows, self.timeout if timeout is None else timeout, **crit)

    def has_text(self, pattern: str) -> bool:
        return uia.find_in(self.windows(), 0, title_re=pattern) is not None

    def wait_os_toast(self, pattern: str, timeout: float | None = None):
        """Windows notification toast (shown by the shell, not by the browser process)."""
        def _find():
            for w in self.desktop.windows():
                n = w.element_info.name or ""
                if "notification" in n.lower() or w.element_info.class_name == "Windows.UI.Core.CoreWindow":
                    hit = uia.descendants(w, title_re=pattern)
                    if hit:
                        return hit[0]
            return None
        return poll(_find, self.timeout if timeout is None else timeout, 0.5, f"OS toast /{pattern}/")

    # -- mouse on web content ----------------------------------------------------
    def viewport_rect(self):
        """Screen rectangle (physical px) of the web content area of the active tab."""
        main = self.main_window()
        hits = uia.descendants(main, class_name="Chrome_RenderWidgetHostHWND")
        hits = [h for h in hits if h.is_visible()] or uia.descendants(main, control_type="Document")
        return hits[0].rectangle()

    def viewport_origin(self) -> tuple[int, int]:
        r = self.viewport_rect()
        return r.left, r.top

    def web_point(self, web, el, offset: tuple[int, int] = (0, 0)) -> tuple[int, int]:
        """Screen coordinates of the center of a web element (top-level document only)."""
        web.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        x, y, dpr = web.driver.execute_script(
            "const r = arguments[0].getBoundingClientRect();"
            "return [r.left + r.width / 2, r.top + r.height / 2, window.devicePixelRatio];", el)
        ox, oy = self.viewport_origin()
        return int(ox + (x + offset[0]) * dpr), int(oy + (y + offset[1]) * dpr)

    def click_web_element(self, web, loc) -> None:
        from pywinauto import mouse

        mouse.click(coords=self.web_point(web, web.find(loc)))

    def drag(self, start: tuple[int, int], end: tuple[int, int], steps: int = 15) -> None:
        """Real mouse drag between two screen points."""
        from pywinauto import mouse

        mouse.press(coords=start)
        for i in range(1, steps + 1):
            mouse.move(coords=(start[0] + (end[0] - start[0]) * i // steps,
                               start[1] + (end[1] - start[1]) * i // steps))
            time.sleep(0.02)
        time.sleep(0.2)
        mouse.release(coords=end)

    def drag_web_element(self, web, src, dst, offset: tuple[int, int] = (0, 0)) -> None:
        self.focus()
        self.drag(self.web_point(web, src), self.web_point(web, dst, offset))

    def drag_file_from_explorer(self, path: str | Path, web=None, target=None) -> None:
        """Real OS drag of a file/folder from File Explorer into the browser.

        This is the only way to test "drop a .crx (or an unpacked folder) on the add-ons
        page": the browser installs from the OS drag data, synthetic JS/CDP drops are ignored.
        Explorer is opened on the file and placed on the left, the browser on the right,
        then the item is dragged onto ``target`` (web locator) or the middle of the page.
        """
        import subprocess

        from pywinauto.controls.hwndwrapper import HwndWrapper

        path = Path(path).resolve()
        subprocess.Popen(["explorer.exe", f"/select,{path}"])
        explorer = poll(lambda: next((w for w in self.desktop.windows(class_name="CabinetWClass")
                                      if path.parent.name.lower() in (w.element_info.name or "").lower()), None),
                        self.timeout, 0.5, f"File Explorer window for {path.parent}")
        main = self.main_window()
        old = main.rectangle()
        try:
            HwndWrapper(explorer.handle).move_window(0, 0, 700, 600)
            HwndWrapper(main.handle).move_window(710, 0, 1200, 900)
            time.sleep(0.5)
            item = uia.find_in([explorer], self.timeout, control_type="ListItem", title=path.name)
            start = item.rectangle().mid_point()
            if web is not None and target is not None:
                end = self.web_point(web, web.find(target))
            else:
                r = self.viewport_rect()
                end = (r.mid_point().x, r.mid_point().y)
            explorer.set_focus()
            self.drag((start.x, start.y), end, steps=30)
        finally:
            try:
                explorer.close()
            except Exception:  # noqa: BLE001
                pass
            HwndWrapper(main.handle).move_window(old.left, old.top, old.width(), old.height())

    def drag_web_to_ui(self, web, src, ui_name) -> None:
        """Drag a web element (e.g. a link) onto browser UI such as the bookmarks bar."""
        r = self.element(ui_name).rectangle()
        self.drag(self.web_point(web, web.find(src)), (r.mid_point().x, r.mid_point().y))

    # -- evidence ----------------------------------------------------------------
    def dump(self, path: str | Path | None = None) -> str:
        """UIA tree of every browser window. Use it to discover names for native_ui.yaml."""
        text = "\n\n".join(uia.dump(w) for w in self.windows())
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text, encoding="utf-8")
        return text

    def screenshot(self, path: str | Path) -> Path:
        """Whole-screen capture (shows native dialogs that a WebDriver screenshot misses)."""
        from PIL import ImageGrab

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(all_screens=True).save(path)
        return path

    def close_stray_dialogs(self) -> int:
        """Press Esc on leftover bubbles/dialogs so the next step starts clean."""
        closed = 0
        main = self.main_window()
        for w in self.windows():
            if w.handle != main.handle and w.element_info.control_type in ("Window", "Dialog", "Pane"):
                try:
                    w.type_keys("{ESC}")
                    closed += 1
                except Exception:  # noqa: BLE001
                    pass
        return closed
