"""Check that this machine can run the suite, step by step, and say what to fix.

    python -m sbtest.tools.doctor                 # uses config/local.yaml
    python -m sbtest.tools.doctor --exe "C:\\build\\SamsungInternet.exe"

Checks: Python + packages, exe, Chromium version detection, chromedriver, browser start,
internal pages, native UI (pywinauto finds the window and the toolbar entries of
config/native_ui.yaml), proxy variables. Screenshots of the browser and the screen are saved
to artifacts/doctor/ so a human or agent can see what the browser looked like.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
import traceback

from sbtest.reporting.cleanup import clear_dir
from sbtest.tools.common import base_parser, make_config

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
results: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f": {detail}" if detail else ""), flush=True)


def main(argv=None) -> int:
    p = base_parser(__doc__.split("\n")[0])
    p.add_argument("--skip-native", action="store_true")
    args = p.parse_args(argv)
    cfg = make_config(args)
    out = cfg.path("paths.artifacts") / "doctor"     # the latest check only
    clear_dir(out, cfg.path("paths.artifacts"))

    report(OK if sys.version_info >= (3, 10) else FAIL, "python", sys.version.split()[0] + " (need 3.10+)")
    for mod in ("selenium", "pytest", "yaml", "psutil", "PIL", "pytest_html"):
        report(OK if importlib.util.find_spec(mod) else FAIL, f"package {mod}",
               "" if importlib.util.find_spec(mod) else "pip install -r requirements.txt")
    if os.name == "nt":
        report(OK if importlib.util.find_spec("pywinauto") else FAIL, "package pywinauto")
        _check_typing()
    else:
        report(WARN, "platform", "not Windows: native UI checks are skipped (Samsung Internet is Windows-only)")
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
        if os.environ.get(var) or os.environ.get(var.lower()):
            report(OK, f"env {var}", os.environ.get(var) or os.environ.get(var.lower()))
    from sbtest.browser.driver_resolver import curl_exe

    curl = curl_exe()
    report(OK if curl else WARN, "download tool", f"curl {curl} (chromedriver downloads)" if curl
           else "no curl.exe: chromedriver is downloaded with Python urllib (may fail behind TLS inspection)")

    exe = str(cfg.path("browser.exe")) if cfg.get("browser.exe") else ""
    if not exe or not os.path.exists(exe):
        report(FAIL, "browser exe", f"{exe!r} not found - set browser.exe in config/local.yaml or --exe")
        return _summary()
    report(OK, "browser exe", exe)

    from sbtest.browser.session import BrowserSession

    session = BrowserSession(cfg, name="doctor", out_dir=out)
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
        report(FAIL, "browser start", f"{type(e).__name__}: {str(e).splitlines()[0]} - see artifacts/doctor/logs/; "
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
                       + ("the browser crashed/closed: see artifacts/doctor/logs/" if crashed else "check pages.scheme"))
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
                    # bookmark_star is not checked: Samsung only shows it on a bookmarked page
                    for key in ("omnibox", "back_button", "reload_button", "app_menu_button"):
                        found = nb.exists(key)
                        report(OK if found else WARN, f"native ui_map {key}",
                               "" if found else "not found - fix config/native_ui.yaml (python -m sbtest.tools.uia_dump)")
                    nb.dump(out / "uia.txt")
                    nb.screenshot(out / "screen.png")
            except Exception as e:  # noqa: BLE001
                report(FAIL, "native", f"{type(e).__name__}: {e} - is the desktop unlocked and visible?")
    finally:
        session.stop()

    print(f"\nScreenshots and dumps: {out}")
    return _summary()


IME_PROCESSES = {"unikeynt.exe": "UniKey", "unikey.exe": "UniKey", "evkey.exe": "EVKey", "evkey64.exe": "EVKey",
                 "openkey.exe": "OpenKey", "gotiengviet.exe": "GoTiengViet"}


def _check_typing() -> None:
    """Native steps type paths and names with the real keyboard: an input method (Vietnamese
    Telex/VNI tools, a non-English layout) rewrites what is typed and breaks those steps."""
    try:
        import ctypes

        import psutil

        layout = ctypes.windll.user32.GetKeyboardLayout(0) & 0xFFFF
        report(OK if layout == 0x0409 else WARN, "keyboard layout",
               f"0x{layout:04x}" + ("" if layout == 0x0409 else " - switch to English (US) while tests run"))
        running = sorted({IME_PROCESSES[p.info["name"].lower()] for p in psutil.process_iter(["name"])
                          if (p.info["name"] or "").lower() in IME_PROCESSES})
        report(WARN if running else OK, "input method",
               f"{', '.join(running)} running - turn it off (English mode) while tests run" if running else "none")
    except Exception as e:  # noqa: BLE001 - informative only
        report(WARN, "keyboard check", f"{type(e).__name__}: {e}")


def _summary() -> int:
    fails = [r for r in results if r[0] == FAIL]
    warns = [r for r in results if r[0] == WARN]
    print(f"\n{len(results) - len(fails) - len(warns)} ok, {len(warns)} warning(s), {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
