"""(Windows) Dump the UI Automation tree of the browser - to find names for config/native_ui/<target>.yaml.

    python -m sbtest.tools.uia_dump                         # start browser, dump main window
    python -m sbtest.tools.uia_dump --url /pages/page1.html --keys "^d" --out artifacts/uia_bubble.txt
    python -m sbtest.tools.uia_dump --pid 1234              # attach to an already running browser
    python -m sbtest.tools.uia_dump --find "(?i)bookmark"   # only elements whose name matches

``--keys`` sends pywinauto keys after opening the URL (e.g. ``^d`` opens the bookmark
bubble, ``%f`` / ``%e`` opens the app menu) so you can dump the UI that appears.
Each line: ``ControlType 'name' auto_id=.. class=.. rect=..`` -> use as criteria:
``{control_type: Button, title_re: "(?i)^done$"}``.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from sbtest.tools.common import base_parser, make_config, resolve_url, start


def main(argv=None) -> int:
    p = base_parser(__doc__.split("\n")[0])
    p.add_argument("--url", default="", help="page to open first")
    p.add_argument("--keys", action="append", default=[], help="pywinauto keys to send (repeatable)")
    p.add_argument("--wait", type=float, default=1.5)
    p.add_argument("--pid", type=int, help="attach to a running browser process instead of starting one")
    p.add_argument("--find", help="regex: list only elements whose name matches")
    p.add_argument("--out", help="write to file")
    args = p.parse_args(argv)

    from sbtest.native import require, uia

    require()
    session = site = None
    try:
        if args.pid:
            from sbtest.native.browser_ui import NativeBrowser

            nb = NativeBrowser(args.pid, make_config(args))
        else:
            session, site = start(args, "uia")
            if args.url:
                session.web.open(resolve_url(session.cfg, site, args.url))
            nb = session.native
        for k in args.keys:
            time.sleep(args.wait)
            nb.hotkey(k)
        time.sleep(args.wait)
        if args.find:
            rx = re.compile(args.find)
            lines = []
            for w in nb.windows():
                for e in uia.descendants(w):
                    i = uia.info(e)
                    if rx.search(i["name"] or ""):
                        lines.append(f"{i['control_type']} {i['name']!r} auto_id={i['auto_id']!r} "
                                     f"class={i['class_name']!r} rect={i['rect']}")
            text = "\n".join(lines)
        else:
            text = nb.dump()
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"UIA dump written to {args.out}")
        else:
            sys.stdout.write(text + "\n")
    finally:
        if session:
            session.stop()
        if site:
            site.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
