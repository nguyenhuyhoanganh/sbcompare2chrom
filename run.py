"""Run the automated browser tests.

    python run.py --all                                  # Samsung Internet, every feature
    python run.py --feature addons,bookmarks             # some features
    python run.py --case ADD-001,DL-004                  # some test cases
    python run.py --sanity                               # quick pass (@sanity)
    python run.py --target chrome --suite reference      # interaction reference suite on Chrome
    python run.py --target chrome --suite all            # reference + feature tests on Chrome
    python run.py --list                                 # cases per feature and automation status
    python run.py --feature downloads -- -x -k pause     # extra pytest args after --

Targets: samsung (default; exe from config/local.yaml or --exe) and chrome (Chrome for Testing
from `python -m sbtest.tools.get_chrome`, or any Chrome via --exe).
Suites: features (tests/features, default for samsung), reference (tests/reference),
all (default for chrome).

Outputs in artifacts/runs/<timestamp>/:
  report/index.html   the sanity report of the build: one row per case (ID, name, steps, expected,
                      result, screenshot of how it ended) + verdict BUILD PASSED / FAILED
  confluence/         the same report as a Confluence page + attachments (Confluence skill uploads it)
  failures/<test>/    failure.txt, page.png (element outlined), screen.png, dom.txt, uia.txt
  results.json, junit.xml, report.html (raw pytest report), steps/ with --screenshot-steps
Rebuild the report of a run: python -m sbtest.tools.report [run_dir] [--open]
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SUITES = {"features": ["tests/features"], "reference": ["tests/reference"], "all": ["tests/features", "tests/reference"]}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]

    p = argparse.ArgumentParser(description="Samsung Internet automated tests")
    p.add_argument("--target", choices=["samsung", "chrome"], help="browser under test (default: config, samsung)")
    p.add_argument("--suite", choices=sorted(SUITES), help="which tests (default: features on samsung, all on chrome)")
    p.add_argument("--exe", help="browser executable (overrides config)")
    p.add_argument("--driver", help="chromedriver path (default: auto)")
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--all", action="store_true", help="every test of the suite (default)")
    sel.add_argument("--feature", help="comma list: addons,bookmarks,downloads,history,settings,general,reference")
    sel.add_argument("--case", help="comma list of case ids, e.g. ADD-001,BM-003")
    p.add_argument("--sanity", action="store_true", help="only tests marked sanity")
    p.add_argument("--no-native", action="store_true", help="skip tests that drive native UI")
    p.add_argument("--headless", action="store_true", help="headless browser (implies --no-native)")
    p.add_argument("--scope", choices=["function", "module", "session"], help="browser reuse scope")
    p.add_argument("--reruns", type=int, default=0, help="re-run failed tests N times (separate flakes)")
    p.add_argument("--keep-profile", action="store_true", help="keep profile folders")
    p.add_argument("--screenshot-steps", action="store_true", help="screenshot after every test step")
    p.add_argument("--list", action="store_true", help="print test cases and automation status, then exit")
    args = p.parse_args(argv)

    if args.list:
        from sbtest.tools.coverage import main as coverage_main
        return coverage_main([])

    import pytest

    from sbtest.config import load_config

    target = load_config({"target": args.target}).target
    suite = args.suite or ("all" if target == "chrome" else "features")
    run_dir = ROOT / "artifacts" / "runs" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    pargs = [str(ROOT / s) for s in SUITES[suite]]
    pargs += ["--target", target, "--run-dir", str(run_dir), f"--junitxml={run_dir / 'junit.xml'}",
              "-p", "no:cacheprovider"]
    if importlib.util.find_spec("pytest_html"):  # optional; find_spec avoids importing it too early
        pargs += [f"--html={run_dir / 'report.html'}", "--self-contained-html"]
    for flag, value in (("--exe", args.exe), ("--driver", args.driver), ("--feature", args.feature),
                        ("--case", args.case), ("--browser-scope", args.scope)):
        if value:
            pargs += [flag, value]
    for flag, on in (("--headless", args.headless), ("--keep-profile", args.keep_profile),
                     ("--screenshot-steps", args.screenshot_steps)):
        if on:
            pargs.append(flag)
    marks = (["sanity"] if args.sanity else []) + (["not native"] if args.no_native or args.headless else [])
    if marks:
        pargs += ["-m", " and ".join(marks)]
    if args.reruns:
        pargs += ["--reruns", str(args.reruns)]
    pargs += extra
    print("pytest", " ".join(pargs))
    code = pytest.main(pargs)
    print(f"\nArtifacts: {run_dir}")
    if (run_dir / "report" / "index.html").exists():
        print(f"Sanity report: {run_dir / 'report' / 'index.html'}")
    if (run_dir / "confluence" / "manifest.json").exists():
        print(f"Confluence-ready report: {run_dir / 'confluence'} (upload with the Confluence skill)")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
