"""Second half of setup.bat (the first half installs Python packages): make sure the browser
exe is configured and check the machine (doctor, which also gets chromedriver). Running the
tests is a separate command: ``python run.py ...``.

    setup.bat                                        install + check (exe from config/local.yaml)
    setup.bat --exe "C:\\build\\SamsungInternet.exe"     check that build (not saved)

Without --exe it uses browser.exe of config/local.yaml; when that is missing it looks in the
usual install folders and asks (the answer is saved to config/local.yaml).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from sbtest.config import ROOT
from sbtest.tools import console
from sbtest.tools.console import FAIL, OK, WARN

LOCAL = ROOT / "config" / "local.yaml"
INSTALL_DIRS = [os.environ.get(v, "") for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
EXE_NAMES = ("samsunginternet.exe", "SamsungInternet.exe")


def installed_exe() -> str:
    """Samsung Browser in the usual install folders (public installer), or ""."""
    for base in filter(None, INSTALL_DIRS):
        for name in EXE_NAMES:
            p = Path(base) / "Samsung" / "Internet" / "Application" / name
            if p.exists():
                return str(p)
    return ""


def save_exe(path: str, local: Path = LOCAL) -> None:
    """Write ``browser.exe`` into local.yaml, keeping the rest of the file and its comments."""
    example = local.parent / "local.example.yaml"   # a new local.yaml starts from the commented example
    text = (local if local.exists() else example).read_text(encoding="utf-8") if (
        local.exists() or example.exists()) else ""
    line = f"exe: '{path}'"
    m = re.search(r"^(browser:\s*\n(?:[ \t]*#.*\n)*)([ \t]+)exe:.*$", text, re.M)
    if m:
        text = text[:m.start()] + m.group(1) + m.group(2) + line + text[m.end():]
    elif re.search(r"^browser:\s*$", text, re.M):
        text = re.sub(r"^browser:\s*$", "browser:\n  " + line, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + ("\n\n" if text else "") + "browser:\n  " + line + "\n"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(text, encoding="utf-8")


def ensure_exe(cli_exe: str | None) -> str | None:
    """The exe to test: --exe, else browser.exe of the config, else found/asked and saved."""
    console.section("3/4", "Browser to test")
    if cli_exe:
        ok = Path(cli_exe).exists()
        console.check(OK if ok else FAIL, f"Using --exe {cli_exe}", "the file does not exist: check the path")
        return cli_exe if ok else None
    from sbtest.config import load_config

    configured = load_config().get("browser.exe") or ""
    if configured and Path(configured).exists():
        console.check(OK, f"browser.exe in config\\local.yaml: {configured}")
        return configured
    if configured and LOCAL.exists():
        console.check(WARN, f"browser.exe in config\\local.yaml does not exist: {configured}")
    found = installed_exe()
    while True:
        hint = f" [Enter = {found}]" if found else ""
        prompted = False
        try:
            if not sys.stdin.isatty():
                raise EOFError
            prompted = True
            answer = input(f"  Path of SamsungInternet.exe to test{hint}: ").strip().strip('"')
        except EOFError:   # nobody to ask (an agent, "< nul" - NUL even claims to be a terminal)
            if prompted:
                print()   # end the unanswered question line
            if found:
                save_exe(found)
                console.check(OK, f"Found Samsung Browser: {found} (saved to config\\local.yaml)")
                return found
            console.check(FAIL, "No Samsung Browser to test",
                          ".\\setup.bat --exe \"<path of SamsungInternet.exe>\"")
            return None
        path = answer or found
        if path and Path(path).is_file():
            save_exe(path)
            console.check(OK, f"Saved to config\\local.yaml: {path}")
            return path
        console.check(WARN, f"Not a file: {path!r}", "paste the full path, e.g. C:\\build\\SamsungInternet.exe")


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="setup.bat: check the machine after installing")
    p.add_argument("--exe", help="SamsungInternet.exe to check (default: browser.exe of config/local.yaml)")
    args = p.parse_args(argv)

    if not ensure_exe(args.exe):
        return 1
    console.section("4/4", "Machine check")
    console.note("the browser opens and closes by itself")
    from sbtest.tools import doctor

    code = doctor.main(["--exe", args.exe] if args.exe else [], step="4")
    if code:
        return code
    exe = f' --exe "{args.exe}"' if args.exe else ""
    print("\nNext - run the tests (hands off the mouse and keyboard while they run):")
    print(f"  .venv\\Scripts\\python run.py --sanity{exe}      quick sanity pass")
    print(f"  .venv\\Scripts\\python run.py --all{exe}         every test (about 8-10 minutes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
