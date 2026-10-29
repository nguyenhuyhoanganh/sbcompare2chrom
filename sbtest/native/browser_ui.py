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


def _explorer_item(explorer, path: Path):
    """ListItem of ``path`` in an Explorer window when extensions are hidden: the selected
    item named like the stem (explorer.exe /select selects it), else the first stem match."""
    hits = uia.descendants(explorer, control_type="ListItem", title=path.stem)
    for h in hits:
        try:
            if h.is_selected():
                return h
        except Exception:  # noqa: BLE001
            pass
    if not hits:
        raise LookupError(f"{path.name} not listed in Explorer {explorer.element_info.name!r}")
    return hits[0]


def _bubble_of(el):
    """Nearest ancestor that is a Views bubble (its own Chrome_WidgetWin_1 / RootView)."""
    node = el
    for _ in range(12):
        try:
            node = node.parent()
        except Exception:  # noqa: BLE001
            return None
        if node is None:
            return None
        if node.element_info.class_name in ("Chrome_WidgetWin_1", "RootView", "BubbleFrameView"):
            return node
    return None


class NativeBrowser:
    def __init__(self, pid: int, cfg: Config) -> None:
        require()
        from pywinauto import Desktop

        self.pid = pid
        self.cfg = cfg
        self.timeout = float(cfg.get("timeouts.native", 10))
        self.desktop = Desktop(backend=cfg.get("native.backend", "uia"))
        self.ui_map: dict = yaml.safe_load(cfg.path("native.ui_map").read_text(encoding="utf-8")) or {}
        self._bubbles_until = 0.0     # watch_startup_bubbles: look for them until then
        self._bubbles_next = 0.0      # next look (at most every 0.5 s)

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
            # the window handles of the browser processes only (Win32, fast); wrapping every
            # window of the desktop in UIA first costs seconds with many apps open
            from pywinauto import findwindows
            from pywinauto.controls.uiawrapper import UIAWrapper
            from pywinauto.uia_element_info import UIAElementInfo

            handles = [h for pid in pids for h in findwindows.find_windows(
                process=pid, visible_only=visible_only, top_level_only=True, backend="win32")]
            return [UIAWrapper(UIAElementInfo(h)) for h in handles]
        except Exception as e:  # noqa: BLE001 - fall back to the UIA desktop walk
            log.debug("fast window lookup failed (%s), walking the desktop", e)
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
    def foreground_owner(self) -> tuple[int, str]:
        """(pid, process name) of the window that receives the keyboard now."""
        import ctypes
        from ctypes import wintypes

        import psutil

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            name = psutil.Process(pid.value).name() if pid.value else "nothing (locked screen?)"
        except psutil.Error:
            name = "?"
        return pid.value, name

    def ensure_keyboard_target(self, refocus: bool = True) -> None:
        """Real keystrokes go to the foreground window: make sure it is one of the browser's
        (frame, bubble, its Save As dialog). Another window in front (Windows Widgets, a
        notification, someone using the machine) -> bring the browser back once, then fail
        with the name of the intruder instead of typing into it."""
        def _ours():
            return self.foreground_owner()[0] in self.pids()

        if _ours():
            return
        pid, name = self.foreground_owner()
        log.warning("%s (pid %s) is in front of the browser%s", name, pid, ", bringing the browser back" if refocus else "")
        if refocus:
            self.focus()
        try:
            poll(_ours, 3, 0.1, "browser window in the foreground")
        except TimeoutError:
            pid, name = self.foreground_owner()
            raise RuntimeError(f"keyboard input would go to {name} (pid {pid}), not the browser: another window "
                               "took the foreground - keep the desktop free while native tests run") from None

    def hotkey(self, keys: str, focus: bool = True) -> None:
        """Browser-level shortcut, e.g. ``"^d"`` bookmark, ``"^h"`` history, ``"^j"`` downloads,
        ``"^t"`` new tab, ``"^+{DELETE}"`` clear browsing data, ``"{F11}"`` fullscreen."""
        from pywinauto import keyboard

        self._close_late_bubbles()
        if focus:
            self.focus()
        self.ensure_keyboard_target(refocus=focus)
        uia.mark("keys", label=keys)
        keyboard.send_keys(keys, pause=0.05)

    def type_text(self, text: str) -> None:
        """Type literal text into whatever has focus (escapes pywinauto special chars)."""
        from pywinauto import keyboard

        from sbtest.native.dialogs import _escape_keys

        self.ensure_keyboard_target(refocus=False)   # typing goes to the focused field: never move it
        uia.mark("type", label=repr(text))
        keyboard.send_keys(_escape_keys(text), with_spaces=True, pause=0.02)

    # -- elements by logical name ----------------------------------------------
    def criteria(self, name_or_criteria, **params) -> dict:
        """UIA criteria of a logical name. Map values may hold ``{name}``-style placeholders,
        filled from ``params`` (regex values get them escaped): ``criteria("addons_menu_pin", name="X")``."""
        if isinstance(name_or_criteria, dict):
            crit = dict(name_or_criteria)
        elif name_or_criteria not in self.ui_map:
            raise KeyError(f"{name_or_criteria!r} not in {self.cfg.get('native.ui_map')}")
        else:
            crit = dict(self.ui_map[name_or_criteria])
        if params:
            for k, v in crit.items():
                if isinstance(v, str) and "{" in v:
                    vals = {p: re.escape(str(x)) if k == "title_re" else x for p, x in params.items()}
                    crit[k] = v.format(**vals)
        return crit

    def element(self, name_or_criteria, timeout: float | None = None, in_main: bool = True, **params):
        """Element of the browser UI by logical name (config/native_ui.yaml) or criteria dict."""
        self._close_late_bubbles()
        crit = self.criteria(name_or_criteria, **params)
        roots = (lambda: [self.main_window()]) if in_main else self.windows
        return uia.find_in(roots, self.timeout if timeout is None else timeout, **crit)

    def exists(self, name_or_criteria, in_main: bool = True, **params) -> bool:
        self._close_late_bubbles()
        crit = self.criteria(name_or_criteria, **params)
        roots = [self.main_window()] if in_main else self.windows()
        return uia.find_in(roots, 0, **crit) is not None

    def click(self, name_or_criteria, real_mouse: bool = True, timeout: float | None = None,
              in_main: bool = True, **params) -> None:
        """Click browser UI by logical name or criteria; ``in_main=False`` also searches the
        browser's other windows (add-on popups, bubbles shown as their own window)."""
        el = uia.wait_actionable(self.element(name_or_criteria, timeout, in_main=in_main, **params))
        uia.mark("click", el)
        if real_mouse:
            el.click_input()
        else:
            el.invoke()

    # -- omnibox / tabs ----------------------------------------------------------
    def omnibox_text(self) -> str:
        el = self.element("omnibox")
        try:
            return el.get_value()
        except Exception:  # noqa: BLE001 - no ValuePattern (Samsung: Group "Address and search bar, <url>")
            name = el.element_info.name or el.window_text() or ""
            return name.split(", ", 1)[1] if re.match(r"(?i)address and search bar, ", name) else name

    def focus_page(self) -> None:
        """Move keyboard focus out of the omnibox into the web content, like clicking the page.

        Since build 155 the omnibox shows other icons while it has focus and the bookmark star
        (``PageActionView``) only appears once it loses focus; a page opened by WebDriver can
        leave the focus in the omnibox."""
        main = self.main_window()
        content = [h for h in uia.descendants(main, class_name="Chrome_RenderWidgetHostHWND") if h.is_visible()]
        if content:
            try:
                content[0].set_focus()
                return
            except Exception as e:  # noqa: BLE001 - fall back to a real click
                log.debug("set_focus on web content failed: %s", e)
        from pywinauto import mouse

        r = self.viewport_rect()
        mouse.click(coords=(r.left + 5, r.bottom - 5))   # blank bottom-left corner of the page

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
        """Click through an *already open* native menu by item names (regex prefix, case-insensitive).

        Items already clicked are skipped, so ``("History", "History")`` opens the History
        sub menu and then picks the History entry inside it."""
        clicked: list = []

        def _next(rx):
            def _find():
                for w in self.windows():
                    for mi in uia.descendants(w, control_type="MenuItem", title_re=rx):
                        if mi.element_info.runtime_id not in clicked and mi.is_visible():
                            return mi
                return None
            return _find

        for item in path:
            mi = poll(_next(f"(?i)^{item}"), self.timeout if timeout is None else timeout, 0.3,
                      f"menu item /{item}/ (open items: {self.menu_items()})")
            clicked.append(mi.element_info.runtime_id)
            uia.wait_actionable(mi)   # a sub menu slides open: wait until it stands still
            uia.mark("menu", mi)
            mi.click_input()

    def menu(self, *path: str) -> None:
        """App menu (the "..." / hamburger button) then items, e.g. ``menu("Bookmarks", "Bookmark manager")``."""
        self.click("app_menu_button")
        self.select_menu_items(*path)

    def context_menu_web(self, web, loc, *path: str) -> None:
        """Right-click a web element with the real mouse and pick native context menu items."""
        from pywinauto import mouse

        x, y = self.web_point(web, web.find(loc))
        uia.mark("right-click", point=(x, y))
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
        """A dialog/bubble/prompt by logical name (``config/native_ui.yaml: dialogs``) or title regex.

        Searches top-level windows of the process first, then panes/dialogs inside them
        (Views bubbles are often child panes of the frame)."""
        self._close_late_bubbles()
        pattern = self._dialog_pattern(name_or_regex)
        el = poll(lambda: self._find_dialog(pattern), self.timeout if timeout is None else timeout, 0.3,
                  f"native dialog /{pattern}/")
        return Dialog(el, self.timeout)

    def wait_dialog_gone(self, name_or_regex: str, timeout: float | None = None) -> None:
        """Wait until no dialog/bubble/toast ``name_or_regex`` is shown any more. Use it before
        clicking the button a bubble is anchored to: while the bubble is open, that click only
        closes the bubble."""
        pattern = self._dialog_pattern(name_or_regex)
        poll(lambda: self._find_dialog(pattern) is None, self.timeout if timeout is None else timeout, 0.3,
             f"native dialog /{pattern}/ gone")

    def _dialog_pattern(self, name_or_regex: str) -> str:
        return (self.ui_map.get("dialogs") or {}).get(name_or_regex, name_or_regex)

    def _find_dialog(self, pattern: str):
        rx = re.compile(pattern)
        wins = self.windows()
        for w in wins:
            if rx.search(w.element_info.name or ""):
                return w
        for w in wins:
            for ct in ("Dialog", "Window", "Pane", "Group"):
                hits = uia.descendants(w, control_type=ct, title_re=pattern)
                if hits:
                    return hits[0]
        # unnamed bubbles (Samsung: "Delete X?", "Page bookmarked."): match a text inside
        # and return the bubble's own widget window
        for w in wins:
            for label in uia.descendants(w, control_type="Text", title_re=pattern):
                return _bubble_of(label) or w
        return None

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
        """Web notification popup: drawn by the browser itself (an unnamed Chrome_WidgetWin_1
        bottom right - Chrome for Testing does this) or a Windows shell toast."""
        def _find():
            for w in self.windows():
                if w.element_info.name:  # browser frames have a title; notification popups do not
                    continue
                hit = uia.descendants(w, title_re=pattern)
                if hit:
                    return hit[0]
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
        if hits:
            return hits[0].rectangle()
        # Chrome builds its UIA tree for web content lazily: ask Win32 for the render widget
        from pywinauto import findwindows, handleprops
        handles = [h for h in findwindows.find_windows(parent=main.handle, class_name="Chrome_RenderWidgetHostHWND",
                                                       top_level_only=False) if handleprops.isvisible(h)]
        if not handles:
            raise LookupError("web content area not found (no Chrome_RenderWidgetHostHWND / Document)")
        rects = [handleprops.rectangle(h) for h in handles]
        return max(rects, key=lambda r: r.width() * r.height())

    def viewport_origin(self) -> tuple[int, int]:
        r = self.viewport_rect()
        return r.left, r.top

    def web_point(self, web, el, offset: tuple[int, int] = (0, 0)) -> tuple[int, int]:
        """Screen coordinates of the center of a web element (top-level document only)."""
        self._close_late_bubbles()   # a real mouse action on the page: nothing may cover it
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

        uia.mark("drag", point=start)
        uia.mark("drop", point=end)
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

    def wait_explorer(self, folder_name: str, timeout: float | None = None) -> Dialog:
        """A File Explorer window showing ``folder_name`` (e.g. opened by "Show in folder")."""
        def _find():
            for w in self.desktop.windows(class_name="CabinetWClass"):
                if folder_name.lower() in (w.element_info.name or "").lower():
                    return w
            return None
        return Dialog(poll(_find, self.timeout if timeout is None else timeout, 0.5, f"Explorer '{folder_name}'"),
                      self.timeout)

    def explorer_selected(self, explorer: Dialog) -> list[str]:
        """Names of the selected items in an Explorer window."""
        out = []
        for item in uia.descendants(explorer.el, control_type="ListItem"):
            try:
                if item.is_selected():
                    out.append(item.element_info.name)
            except Exception:  # noqa: BLE001 - item without SelectionItem pattern
                pass
        return out

    def explorer_has_selected(self, explorer: Dialog, filename: str) -> bool:
        """Is ``filename`` selected in Explorer? Matches the name with or without its extension
        (Explorer hides known extensions by default)."""
        stem = Path(filename).stem
        return any(n in (filename, stem) for n in self.explorer_selected(explorer))

    def drag_file_from_explorer(self, path: str | Path, web=None, target=None) -> None:
        """Real OS drag of a file/folder from File Explorer into the browser.

        Use it when the browser must receive real OS drag data (synthetic JS/CDP drops of
        files are ignored by some pages, e.g. the add-ons page).
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
            # Explorer hides known extensions by default ("report" for report.pdf, maybe next
            # to a folder of the same name): prefer the exact name, then the stem
            item = (uia.find_in([explorer], 2, control_type="ListItem", title=path.name)
                    if uia.find_in([explorer], 0, control_type="ListItem", title=path.name)
                    else _explorer_item(explorer, path))
            uia.wait_actionable(item)   # Explorer lays its items out again after the resize
            # the item rectangle can span past the (just shrunk) window in Details view: press
            # on the start of the name, clamped inside the Explorer window
            ir, er = item.rectangle(), explorer.rectangle()
            start = (min(ir.left + 60, er.right - 30), (ir.top + ir.bottom) // 2)
            if web is not None and target is not None:
                end = self.web_point(web, web.find(target))
            else:
                r = self.viewport_rect()
                end = (r.mid_point().x, r.mid_point().y)
            explorer.set_focus()
            self.drag(start, end, steps=30)
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
        """UIA tree of every browser window. Use it to discover names for config/native_ui.yaml."""
        text = "\n\n".join(uia.dump(w) for w in self.windows())
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text, encoding="utf-8")
        return text

    def window_rect(self) -> tuple[int, int, int, int]:
        """Screen box (left, top, right, bottom) around every visible window of the browser:
        the frame plus its bubbles, menus, prompts and file dialogs (other apps excluded)."""
        boxes = []
        for w in self.windows():
            try:
                r = w.rectangle()
            except Exception:  # noqa: BLE001 - window vanished
                continue
            # minimized windows sit at -32000; zero-size ones are helper windows
            if r.width() > 0 and r.height() > 0 and r.left > -30000 and r.top > -30000:
                boxes.append((r.left, r.top, r.right, r.bottom))
        if not boxes:
            raise LookupError(f"no visible window of browser pid {self.pid}")
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    def screenshot(self, path: str | Path, whole_screen: bool = False) -> Path:
        """Picture of the browser's windows as they are on screen (native bubbles and dialogs
        included, which a WebDriver screenshot misses). ``whole_screen`` = every monitor."""
        from PIL import ImageGrab

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=None if whole_screen else self.window_rect(), all_screens=True).save(path)
        return path

    def dismiss_startup_bubbles(self, timeout: float = 0) -> list[str]:
        """Close the bubbles a fresh profile can show on start (``startup_bubbles`` in the
        ui map, e.g. Samsung's "has been updated"), so they do not cover the page or toolbar.
        One quick look by default; ``timeout`` > 0 keeps looking that long."""
        rules = self.ui_map.get("startup_bubbles") or []
        closed: list[str] = []
        deadline = time.monotonic() + timeout
        while rules and len(closed) < len(rules):
            for rule in rules:
                if rule["text"] in closed:
                    continue
                for w in self.windows():
                    # the label is a Text (views::Label): a native UIA search, not a full walk
                    label = uia.find_in([w], 0, control_type="Text", title_re=rule["text"])
                    if label is None:
                        continue
                    # the button lives in the same bubble: walk up until a container has it
                    node = label
                    for _ in range(6):
                        node = node.parent()
                        if node is None:
                            break
                        btn = uia.find_in([node], 0, control_type="Button", title=rule["button"])
                        if btn is not None:
                            btn.invoke()
                            closed.append(rule["text"])
                            log.info("dismissed startup bubble /%s/", rule["text"])
                            break
                    break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.3)
        return closed

    def watch_startup_bubbles(self, seconds: float) -> None:
        """For the next ``seconds``, every native action first closes a startup bubble that
        has shown up meanwhile - nobody waits for a bubble that may never come (the test starts
        right away; it shows on some starts only)."""
        if self.ui_map.get("startup_bubbles"):
            self._bubbles_until = time.monotonic() + seconds

    def _close_late_bubbles(self) -> None:
        now = time.monotonic()
        if not self._bubbles_until or now < self._bubbles_next:
            return
        if now >= self._bubbles_until:
            self._bubbles_until = 0.0
            return
        self._bubbles_next = now + 0.5
        try:
            if self.dismiss_startup_bubbles():
                self._bubbles_until = 0.0   # closed: nothing more to watch
        except Exception as e:  # noqa: BLE001 - never fail an action because of this check
            log.debug("startup bubble check failed: %s", e)

    def close_download_bubble(self, timeout: float = 3) -> bool:
        """Close the toolbar Downloads bubble that opens when a download finishes (since build
        155 it covers the toolbar of the downloads page, e.g. "Clear download history"): click
        its X, Esc when it has none. False when no bubble showed up within ``timeout``."""
        try:
            row = self.element("download_bubble_item", timeout=timeout, in_main=False)
        except TimeoutError:
            return False
        frame = _bubble_of(row)
        if frame is not None and frame.element_info.handle == self.main_window().element_info.handle:
            frame = None   # never search the browser frame: tab close buttons are named "Close" too
        bubble = Dialog(frame or row, self.timeout)
        close = uia.find_in([bubble.el], 1, **self.criteria("download_bubble_close")) if frame else None
        if close is not None:
            uia.wait_actionable(close)
            uia.mark("click", close)
            close.click_input()
        else:
            bubble.press("{ESC}")
        poll(lambda: not self.exists("download_bubble_item", in_main=False), self.timeout, 0.3,
             "Downloads bubble closed")
        return True

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
