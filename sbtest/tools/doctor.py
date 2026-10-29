"""Check that this machine can run the suite, step by step, and say what to fix.

    python -m sbtest.tools.doctor                 # uses config/local.yaml
    python -m sbtest.tools.doctor --exe "C:\\build\\SamsungInternet.exe"

Checks: Python + packages, keyboard, download tool, exe, Chromium version, chromedriver,
browser start, internal pages, native UI (the toolbar entries of config/native_ui.yaml).
One line per check; problems carry a "fix:" line. Screenshots, dumps and the technical log
(doctor.log) go to artifacts/doctor/. ``setup.bat`` runs this after installing.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

from sbtest.reporting.cleanup import clear_dir
from sbtest.tools import console
from sbtest.tools.common import base_parser, make_config
from sbtest.tools.console import FAIL, OK, WARN

results: list[str] = []
SECTIONS = 5

PACKAGES = {"selenium": "selenium", "pytest": "pytest", "yaml": "PyYAML", "psutil": "psutil", "PIL": "Pillow",
            "pytest_html": "pytest-html"}
WINDOWS_PACKAGES = {"pywinauto": "pywinauto", "win32api": "pywin32"}
PAGES = {"extensions": "Add-ons", "bookmarks": "Bookmarks", "history": "History", "downloads": "Downloads",
         "settings": "Settings", "version": "About version"}
NATIVE_KEYS = {"omnibox": "address bar", "back_button": "Back", "reload_button": "Reload",
               "app_menu_button": "app menu"}


_step = ""   # "4" when setup runs the doctor as its step 4 -> sections 4.1 .. 4.5


_shown = 0


def _section(text: str) -> None:
    global _shown
    _shown += 1
    console.section(f"{_step}.{_shown}" if _step else f"{_shown}/{SECTIONS}", text)


def report(status: str, text: str, fix: str = "") -> None:
    results.append(status)
    console.check(status, text, fix)


def main(argv=None, step: str = "") -> int:
    """``step``: number of the setup step this check runs as (no title box then)."""
    global _step, _shown
    _step, _shown = step, 0
    p = base_parser(__doc__.split("\n")[0])
    p.add_argument("--skip-native", action="store_true")
    args = p.parse_args(argv)
    results.clear()
    from sbtest.config import load_config

    out = load_config().path("paths.artifacts") / "doctor"     # the latest check only
    clear_dir(out, out.parent)
    console.log_to_file(out / "doctor.log", verbose=args.verbose)
    cfg = make_config(args)

    if not step:
        console.title("sbtest doctor - can this machine run the tests?")
    if not step:   # setup.bat has just checked Python and installed the packages
        _python_and_packages()
    _keyboard_and_network()
    session = _browser_files(cfg, out)
    if session is not None:
        try:
            if _browser_start(session):
                _internal_pages(cfg, session, out)
                _native(session, out, skip=args.skip_native)
        finally:
            session.stop()
    return _summary(out)


# -- 1 -------------------------------------------------------------------------------
def _python_and_packages() -> None:
    _section("Python and packages")
    v = sys.version.split()[0]
    report(OK if sys.version_info >= (3, 10) else FAIL, f"Python {v}",
           "install Python 3.10 or newer from python.org, then run setup.bat again")
    wanted = {**PACKAGES, **(WINDOWS_PACKAGES if os.name == "nt" else {})}
    missing = [pip for mod, pip in wanted.items() if not importlib.util.find_spec(mod)]
    if missing:
        report(FAIL, f"Missing packages: {', '.join(missing)}", "run setup.bat (it installs requirements.txt)")
    else:
        report(OK, f"All {len(wanted)} required packages installed")


# -- 2 -------------------------------------------------------------------------------
IME_PROCESSES = {"unikeynt.exe": "UniKey", "unikey.exe": "UniKey", "evkey.exe": "EVKey", "evkey64.exe": "EVKey",
                 "openkey.exe": "OpenKey", "gotiengviet.exe": "GoTiengViet"}


def _keyboard_and_network() -> None:
    _section("Keyboard and network")
    if os.name != "nt":
        report(WARN, "Not Windows: the browser UI checks are skipped (Samsung Browser is Windows-only)")
    else:
        _check_typing()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        report(OK, f"Proxy for downloads: {proxy}")
    from sbtest.browser.driver_resolver import curl_exe

    curl = curl_exe()
    report(OK if curl else WARN, f"Download tool: {curl}" if curl else "No curl.exe found",
           "chromedriver will be downloaded with Python, which fails behind a company SSL check; "
           "copy artifacts\\drivers\\<major>\\chromedriver.exe from another machine if it does")


def _check_typing() -> None:
    """Native steps type paths and names with the real keyboard: an input method (Vietnamese
    Telex/VNI tools, a non-English layout) rewrites what is typed and breaks those steps."""
    try:
        import ctypes

        import psutil

        layout = ctypes.windll.user32.GetKeyboardLayout(0) & 0xFFFF
        report(OK if layout == 0x0409 else WARN,
               "Keyboard layout: English (US)" if layout == 0x0409 else f"Keyboard layout is not English (0x{layout:04x})",
               "switch to English (US) while the tests run (Win+Space)")
        running = sorted({IME_PROCESSES[p.info["name"].lower()] for p in psutil.process_iter(["name"])
                          if (p.info["name"] or "").lower() in IME_PROCESSES})
        report(WARN if running else OK,
               f"{', '.join(running)} is running" if running else "No Vietnamese input method running",
               "switch it to English mode (or quit it) while the tests run: it changes what the tests type")
    except Exception as e:  # noqa: BLE001 - informative only
        report(WARN, f"Could not check the keyboard ({type(e).__name__})")


# -- 3 -------------------------------------------------------------------------------
def _browser_files(cfg, out):
    """The exe, its Chromium version and chromedriver -> a session ready to start (or None)."""
    _section("Browser and chromedriver")
    exe = str(cfg.path("browser.exe")) if cfg.get("browser.exe") else ""
    if not exe or not os.path.exists(exe):
        report(FAIL, "Samsung Browser not found" + (f" at {exe}" if exe else ""),
               "put the path of SamsungInternet.exe in config\\local.yaml (browser.exe) or pass --exe \"<path>\"")
        return None
    from sbtest.reporting.results import exe_version

    version = exe_version(exe)
    report(OK, f"Samsung Browser {version or '(version unknown)'}: {exe}")
    from sbtest.browser.profile import SHORT_ROOT, profiles_root

    if profiles_root(out / "profiles") == SHORT_ROOT:
        # Chromium cannot open profile files past 260 characters ("Profile error occurred")
        report(OK, f"Browser profiles go to {SHORT_ROOT} (the repo folder is too deep for them)")

    from sbtest.browser.driver_resolver import driver_version

    from sbtest.browser.session import BrowserSession
    from sbtest.config import DRIVERS_DIR, ROOT

    console.note("finding the Chromium version and chromedriver (downloaded if this machine has none)")
    had = set(DRIVERS_DIR.glob("*/chromedriver*"))
    session = BrowserSession(cfg, name="doctor", out_dir=out)
    try:
        chromium, driver = session.resolve()
    except Exception as e:  # noqa: BLE001
        report(FAIL, "No usable chromedriver", f"{str(e).splitlines()[0]}  (details: artifacts\\doctor\\doctor.log)")
        return None
    if chromium:
        report(OK, f"Built on Chromium {chromium}")
    shown = Path(driver).relative_to(ROOT) if Path(driver).is_relative_to(ROOT) else driver
    new = " (downloaded now)" if Path(driver).is_relative_to(ROOT) and Path(driver) not in had else ""
    report(OK, f"chromedriver {driver_version(driver) or ''}: {shown}{new}")
    return session


# -- 4 -------------------------------------------------------------------------------
def _browser_start(session) -> bool:
    _section("Browser start and internal pages")
    try:
        session.start()
        report(OK, "Browser starts and WebDriver connects")
        return True
    except Exception as e:  # noqa: BLE001
        report(FAIL, f"Browser did not start: {str(e).splitlines()[0][:160]}",
               "close other Samsung Browser windows of the test profile and run again; chromedriver log in "
               "artifacts\\doctor\\logs\\ (a fork that Google's chromedriver does not accept needs one built "
               "from the fork: browser.chromedriver)")
        return False


def _internal_pages(cfg, session, out) -> None:
    broken = []
    for name, label in PAGES.items():
        url = cfg.page_url(name)
        try:
            session.web.open(url)
            time.sleep(0.5)
            body = session.web.page_text()
            if "ERR_" in body or not body.strip():
                broken.append(label)
            session.web.screenshot(out / f"page_{name}.png")
        except Exception as e:  # noqa: BLE001
            if "invalid session" in str(e).lower():
                report(FAIL, f"The browser closed or crashed while opening {label}",
                       "see artifacts\\doctor\\logs\\; run doctor again - if it repeats, report the build")
                return
            broken.append(label)
    if broken:
        report(WARN, f"Pages that did not load: {', '.join(broken)}",
               "check pages: in config\\default.yaml; pictures in artifacts\\doctor\\page_*.png")
    else:
        report(OK, f"Internal pages open: {', '.join(PAGES.values())}")


# -- 5 -------------------------------------------------------------------------------
def _native(session, out, skip: bool) -> None:
    _section("Browser UI (toolbar, menus, dialogs)")
    if skip or os.name != "nt":
        report(WARN, "Skipped" + (" (--skip-native)" if skip else " (not Windows)"))
        return
    try:
        nb = session.native
        if nb is None:
            report(WARN, "Browser UI control is off (headless or native.enabled=false)")
            return
        nb.main_window()
        report(OK, "Browser window found")
        missing = [label for key, label in NATIVE_KEYS.items() if not nb.exists(key)]
        if missing:
            report(WARN, f"Not found in the toolbar: {', '.join(missing)}",
                   "the UI changed in this build: update config\\native_ui.yaml (python -m sbtest.tools.uia_dump)")
        else:
            report(OK, f"Toolbar controls found: {', '.join(NATIVE_KEYS.values())}")
        nb.dump(out / "uia.txt")
        nb.screenshot(out / "screen.png")
    except Exception as e:  # noqa: BLE001
        report(FAIL, f"Cannot control the browser window ({type(e).__name__})",
               "the desktop must be unlocked and visible (no minimized remote desktop)")


def _summary(out) -> int:
    fails, warns = results.count(FAIL), results.count(WARN)
    oks = len(results) - fails - warns
    print()
    if fails:
        verdict = console.paint(f"NOT READY - fix the {fails} FAIL line(s) above, then run again", FAIL)
    elif warns:
        verdict = console.paint("READY - the tests can run; read the WARN line(s) above", WARN)
    else:
        verdict = console.paint("READY - this machine can run the tests", OK)
    print(f"{verdict}\n  {oks} ok, {warns} warning(s), {fails} failure(s)")
    print(console.paint(f"  screenshots and technical log: {out}", "dim"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
