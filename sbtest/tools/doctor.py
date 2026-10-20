"""Check that this machine can run the suite, step by step, and say what to fix.

    python -m sbtest.tools.doctor                 # uses config/local.yaml
    python -m sbtest.tools.doctor --exe "C:\\build\\SamsungInternet.exe"
    python -m sbtest.tools.doctor --skip-native --skip-atlassian

Checks: Python + packages, exe, Chromium version detection, chromedriver, browser start,
internal page scheme (internet://...), native UI (pywinauto finds the window and toolbar),
proxy variables, Confluence/Jira token. Screenshots of the browser and the screen are saved
to artifacts/doctor/ so a human or agent can see what the browser looked like.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
import traceback

from sbtest.config import ROOT
from sbtest.tools.common import base_parser, make_config

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
results: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f": {detail}" if detail else ""), flush=True)


def main(argv=None) -> int:
    p = base_parser(__doc__.split("\n")[0])
    p.add_argument("--skip-native", action="store_true")
    p.add_argument("--skip-atlassian", action="store_true")
    args = p.parse_args(argv)
    cfg = make_config(args)
    out = ROOT / "artifacts" / "doctor"
    out.mkdir(parents=True, exist_ok=True)

    report(OK if sys.version_info >= (3, 10) else FAIL, "python", sys.version.split()[0] + " (need 3.10+)")
    for mod in ("selenium", "pytest", "yaml", "psutil", "PIL", "pytest_html"):
        report(OK if importlib.util.find_spec(mod) else FAIL, f"package {mod}",
               "" if importlib.util.find_spec(mod) else "pip install -r requirements.txt")
    if os.name == "nt":
        report(OK if importlib.util.find_spec("pywinauto") else FAIL, "package pywinauto")
    else:
        report(WARN, "platform", "not Windows: native UI checks are skipped (Samsung Internet is Windows-only)")
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
        if os.environ.get(var) or os.environ.get(var.lower()):
            report(OK, f"env {var}", os.environ.get(var) or os.environ.get(var.lower()))

    exe = cfg.get("browser.exe")
    if not exe or not os.path.exists(exe):
        report(FAIL, "browser exe", f"{exe!r} not found - set browser.exe in config/local.yaml or --exe")
        return _summary()
    report(OK, "browser exe", exe)

    from sbtest.browser.session import BrowserSession

    session = BrowserSession(cfg, name="doctor")
    try:
        version, driver = session.resolve()
        report(OK, "chromium version", version or "(not needed: chromedriver configured)")
        report(OK, "chromedriver", driver)
    except Exception as e:  # noqa: BLE001
        report(FAIL, "chromium version / chromedriver", f"{type(e).__name__}: {e}")
        return _summary()

    try:
        session.start()
        caps = session.driver.capabilities
        report(OK, "browser start", f"browserVersion={caps.get('browserVersion')} "
                                    f"chromedriver={(caps.get('chrome') or {}).get('chromedriverVersion', '')[:20]}")
        report(OK, "user agent", session.web.js("return navigator.userAgent"))
    except Exception as e:  # noqa: BLE001
        report(FAIL, "browser start", f"{type(e).__name__}: {str(e).splitlines()[0]} - see artifacts/logs/; "
                                      "try --mode attach or a chromedriver built from the fork")
        traceback.print_exc()
        session.stop()
        return _summary()

    try:
        for name in ("version", "extensions", "bookmarks", "history", "downloads", "settings"):
            url = cfg.page_url(name)
            try:
                session.web.open(url)
                time.sleep(0.5)
                shown = session.web.url
                body = session.web.page_text()[:80].replace("\n", " ")
                bad = not shown.startswith(url.split("//")[0]) or "ERR_" in body or not body.strip()
                report(WARN if bad else OK, f"page {url}", f"-> {shown} | {body!r}")
                session.web.screenshot(out / f"page_{name}.png")
            except Exception as e:  # noqa: BLE001
                crashed = "invalid session" in str(e).lower()
                report(FAIL, f"page {url}", f"{type(e).__name__}: {str(e).splitlines()[0]} - "
                       + ("the browser crashed/closed: see artifacts/logs/" if crashed else "check pages.scheme"))
                if crashed:
                    break

        if not args.skip_native and os.name == "nt":
            try:
                nb = session.native
                if nb is None:
                    report(WARN, "native", "disabled (headless or native.enabled=false)")
                else:
                    main_win = nb.main_window()
                    report(OK, "native main window", f"{main_win.element_info.name!r}")
                    for key in ("omnibox", "back_button", "reload_button", "app_menu_button", "bookmark_star"):
                        found = nb.exists(key)
                        report(OK if found else WARN, f"native ui_map {key}",
                               "" if found else "not found - fix config/native_ui.yaml (python -m sbtest.tools.uia_dump)")
                    nb.dump(out / "uia.txt")
                    nb.screenshot(out / "screen.png")
            except Exception as e:  # noqa: BLE001
                report(FAIL, "native", f"{type(e).__name__}: {e} - is the desktop unlocked and visible?")
    finally:
        session.stop()

    if not args.skip_atlassian:
        if not cfg.get("atlassian.confluence_url"):
            report(WARN, "confluence", "atlassian.confluence_url not set (needed for intake/report)")
        else:
            try:
                from sbtest.atlassian import Atlassian

                at = Atlassian.from_config(cfg)
                at.request("GET", f"{at.confluence_url}/rest/api/space?limit=1")
                report(OK, "confluence", at.confluence_url)
            except Exception as e:  # noqa: BLE001
                report(FAIL, "confluence", f"{e}")
    print(f"\nScreenshots and dumps: {out}")
    return _summary()


def _summary() -> int:
    fails = [r for r in results if r[0] == FAIL]
    warns = [r for r in results if r[0] == WARN]
    print(f"\n{len(results) - len(fails) - len(warns)} ok, {len(warns)} warning(s), {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
