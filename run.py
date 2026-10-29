"""Run the Samsung Browser / Samsung Internet sanity tests (tests/features/).

    python run.py --all                                  # every feature
    python run.py --feature addons,bookmarks             # some features
    python run.py --case ADD-001,DL-004                  # some test cases
    python run.py --sanity                               # quick pass (@sanity)
    python run.py --list                                 # cases per feature and automation status
    python run.py --feature downloads -- -x -k pause     # extra pytest args after --

The exe comes from browser.exe in config/local.yaml (or --exe / SB_EXE).

Outputs in artifacts/test-results/ (the latest run only: emptied when a run starts):
  report/index.html   the sanity report of the build: one row per case (ID, name, steps, expected,
                      result, screenshot of how it ended) + verdict BUILD PASSED / FAILED
  confluence/         the same report as a Confluence page + attachments (Confluence skill uploads it)
  failures/<test>/    failure.txt, page.png (element outlined), screen.png, dom.txt, uia.txt
  results.json, junit.xml, report.html (raw pytest report), steps/ with --screenshot-steps
  logs/               chromedriver logs; profiles/ with --keep-profile
Rebuild the report: python -m sbtest.tools.report [--open]
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]

    p = argparse.ArgumentParser(description="Samsung Internet automated tests")
    p.add_argument("--exe", help="SamsungInternet.exe (overrides config)")
    p.add_argument("--driver", help="chromedriver path (default: auto)")
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--all", action="store_true", help="every test (default)")
    sel.add_argument("--feature", help="comma list: addons,bookmarks,downloads,history,general")
    sel.add_argument("--case", help="comma list of case ids, e.g. ADD-001,BM-003")
    p.add_argument("--sanity", action="store_true", help="only tests marked sanity")
    p.add_argument("--no-native", action="store_true", help="skip tests that drive native UI")
    p.add_argument("--headless", action="store_true", help="headless browser (implies --no-native)")
    p.add_argument("--scope", choices=["function", "module", "session"], help="browser reuse scope")
    p.add_argument("--reruns", type=int, default=0, help="re-run failed tests N times (separate flakes)")
    p.add_argument("--keep-profile", action="store_true", help="keep profile folders")
    p.add_argument("--screenshot-steps", action="store_true",
                   help="a picture before every click/typing (target framed in red) and after every step")
    p.add_argument("--record", action="store_true",
                   help="a video of every test (browser windows, step caption, framed clicks) instead of pictures")
    p.add_argument("--confluence-steps", choices=["failed", "all", "none"],
                   help="which cases get their step pictures on the Confluence page (default: failed)")
    p.add_argument("--raw", action="store_true",
                   help="pytest's own output (tracebacks, captured logs) instead of one line per test")
    p.add_argument("--list", action="store_true", help="print test cases and automation status, then exit")
    args = p.parse_args(argv)

    if args.list:
        from sbtest.tools.coverage import main as coverage_main
        return coverage_main([])

    import pytest

    from sbtest.config import load_config

    run_dir = load_config().path("paths.results")   # emptied by the plugin when the tests start
    pargs = [str(ROOT / "tests" / "features"), f"--junitxml={run_dir / 'junit.xml'}",
              "-p", "no:cacheprovider"]
    if importlib.util.find_spec("pytest_html"):  # optional; find_spec avoids importing it too early
        pargs += [f"--html={run_dir / 'report.html'}", "--self-contained-html"]
    for flag, value in (("--exe", args.exe), ("--driver", args.driver), ("--feature", args.feature),
                        ("--case", args.case), ("--browser-scope", args.scope),
                        ("--confluence-steps", args.confluence_steps)):
        if value:
            pargs += [flag, value]
    for flag, on in (("--headless", args.headless), ("--keep-profile", args.keep_profile),
                     ("--screenshot-steps", args.screenshot_steps), ("--record", args.record)):
        if on:
            pargs.append(flag)
    marks = (["sanity"] if args.sanity else []) + (["not native"] if args.no_native or args.headless else [])
    if marks:
        pargs += ["-m", " and ".join(marks)]
    if args.reruns:
        pargs += ["--reruns", str(args.reruns)]
    if args.raw:
        print("Running tests:", " ".join(a for a in argv if a not in ("--exe", args.exe, "--raw")) or "--all",
              flush=True)
    else:   # one readable line per test (sbtest/reporting/live.py) instead of pytest's own output;
        # -ra of pytest.ini belongs to the terminal plugin that is switched off
        pargs += ["--sb-live", "-p", "no:terminal", "-o", "addopts=-p sbtest.pytest_plugin --strict-markers"]
    pargs += extra
    started = time.time()
    code = pytest.main(pargs)
    results = run_dir / "results.json"
    if results.exists() and results.stat().st_mtime >= started:   # never the summary of an older run
        from sbtest.tools import summary

        print()
        summary.main([])   # verdict, totals per feature, failures, report and Confluence folder
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
