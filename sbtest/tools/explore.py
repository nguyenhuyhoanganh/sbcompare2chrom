"""Exploration helper: drive the real browser through a flow and record every state.

Write a throw-away test in ``tests/_scratch/`` (git-ignored), run it on the build, then read
the pictures and dumps to learn names, selectors and behaviour before writing page objects:

    # tests/_scratch/test_explore_bookmarks.py
    from sbtest.tools.explore import Explorer

    def test_explore(web, native, pages, site):
        x = Explorer(web, native, "bookmarks_panel")          # -> artifacts/explore/bookmarks_panel/
        web.open(site.url("/pages/page1.html"))
        x.snap("page")                                        # screen.png + dom.txt + uia.txt
        x.try_step("open panel", lambda: native.click("bookmarks_button"))
        x.find_native("(?i)static page")                      # print UIA elements whose name matches
        x.esc()

    python -m pytest tests/_scratch/test_explore_bookmarks.py -s -p no:cacheprovider

Each ``snap(name)`` writes ``NN_name.png`` (whole screen: native bubbles included),
``NN_name.dom.txt`` (DOM through shadow roots, every line ends with a ready locator) and
``NN_name.uia.txt`` (browser windows as UIA). ``try_step`` snaps after the action and keeps
going when it fails, so one run shows the whole flow. Delete the scratch file afterwards.
"""
from __future__ import annotations

import re
import time
import traceback
from pathlib import Path

from sbtest.config import ROOT
from sbtest.native import uia
from sbtest.tools.dom import dump_dom


class Explorer:
    def __init__(self, web, native=None, name: str = "explore", out: Path | None = None, settle: float = 1.0) -> None:
        self.web, self.native, self.settle = web, native, settle
        self.out = Path(out) if out else ROOT / "artifacts" / "explore" / name
        self.out.mkdir(parents=True, exist_ok=True)
        self.n = 0

    def snap(self, label: str, dom: bool = True, interactive: bool = False, uia_dump: bool = True) -> Path:
        """Record the current state; returns the screenshot path."""
        time.sleep(self.settle)
        self.n += 1
        base = self.out / f"{self.n:02d}_{re.sub(r'[^A-Za-z0-9_-]+', '_', label)}"
        shot = base.with_suffix(".png")
        if self.native is not None:
            self.native.screenshot(shot)
            if uia_dump:
                self.native.dump(base.with_suffix(".uia.txt"))
        else:
            self.web.screenshot(shot)
        if dom:
            try:
                text = f"# URL: {self.web.url} | tabs: {len(self.web.tabs)}\n" + dump_dom(self.web, interactive)
            except Exception as e:  # noqa: BLE001 - the page may be blocked by a modal browser UI
                text = f"# DOM unavailable: {type(e).__name__}: {e}"
            base.with_suffix(".dom.txt").write_text(text, encoding="utf-8")
        print(f"[explore] {shot}")
        return shot

    def try_step(self, label: str, action, snap: bool = True):
        """Run ``action()``; print the error instead of stopping; snap afterwards."""
        result = None
        try:
            result = action()
            print(f"[explore] OK   {label}")
        except Exception as e:  # noqa: BLE001 - exploration keeps going
            print(f"[explore] FAIL {label}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
            traceback.print_exc(limit=1)
        if snap:
            self.snap(label)
        return result

    def find_native(self, pattern: str, control_type: str | None = None) -> list[dict]:
        """Print (and return) UIA elements of the browser whose name matches ``pattern``."""
        hits = []
        for w in self.native.windows():
            crit = {"title_re": pattern, **({"control_type": control_type} if control_type else {})}
            for el in uia.descendants(w, **crit):
                info = uia.info(el)
                hits.append(info)
                print(f"[explore] UIA {info['control_type']} {info['name']!r} auto_id={info['auto_id']!r} "
                      f"class={info['class_name']!r} rect={info['rect']}")
        return hits

    def find_web(self, text: str) -> list[str]:
        """Print (and return) DOM dump lines containing ``text`` (locator at the end of each line)."""
        lines = [line.strip() for line in dump_dom(self.web).splitlines() if text in line]
        for line in lines:
            print(f"[explore] DOM {line}")
        return lines

    def esc(self) -> None:
        """Press Esc in the browser (closes menus, bubbles, dialogs)."""
        if self.native is not None:
            self.native.hotkey("{ESC}")
        time.sleep(0.4)
