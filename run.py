"""Run the Samsung Internet sanity suite.

    python run.py --exe "C:\\SI\\SamsungInternet.exe" --all
    python run.py --exe ... --feature bookmarks,history
    python run.py --exe ... --case BM-001,DL-004
    python run.py --exe ... --sanity                 # only @pytest.mark.sanity
    python run.py --list                            # features, cases, automation status
    python run.py --exe ... --feature downloads -- -x -k pause   # extra pytest args after --

Reports: artifacts/runs/<timestamp>/report.html, junit.xml, failures/<test>/ (screenshots,
DOM dump, UIA dump). Exit code = pytest exit code.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]

    p = argparse.ArgumentParser(description="Samsung Internet automated sanity tests")
    p.add_argument("--exe", help="SamsungInternet.exe path (or set SB_EXE / config/local.yaml)")
    p.add_argument("--driver", help="chromedriver path (default: auto)")
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--all", action="store_true", help="run every feature (default)")
    sel.add_argument("--feature", help="comma list: bookmarks,history,downloads,settings,addons,general")
    sel.add_argument("--case", help="comma list of case ids, e.g. BM-001,HIS-003")
    p.add_argument("--sanity", action="store_true", help="only tests marked sanity")
    p.add_argument("--no-native", action="store_true", help="skip tests that drive native UI")
    p.add_argument("--headless", action="store_true", help="headless browser (implies --no-native)")
    p.add_argument("--scope", choices=["function", "module", "session"], help="browser reuse scope")
    p.add_argument("--reruns", type=int, default=0, help="re-run failed tests N times (flaky env)")
    p.add_argument("--keep-profile", action="store_true", help="keep profile folders")
    p.add_argument("--list", action="store_true", help="print features/cases and coverage, then exit")
    args = p.parse_args(argv)

    if args.list:
        from sbtest.tools.coverage import main as coverage_main
        return coverage_main([])

    import pytest

    run_dir = ROOT / "artifacts" / "runs" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    pargs = [str(ROOT / "tests"), "--run-dir", str(run_dir), f"--junitxml={run_dir / 'junit.xml'}",
             "-p", "no:cacheprovider"]
    if importlib.util.find_spec("pytest_html"):  # optional; find_spec avoids importing it early
        pargs += [f"--html={run_dir / 'report.html'}", "--self-contained-html"]
    if args.exe:
        pargs += ["--exe", args.exe]
    if args.driver:
        pargs += ["--driver", args.driver]
    if args.feature:
        pargs += ["--feature", args.feature]
    if args.case:
        pargs += ["--case", args.case]
    if args.headless:
        pargs += ["--headless"]
    if args.scope:
        pargs += ["--browser-scope", args.scope]
    if args.keep_profile:
        pargs += ["--keep-profile"]
    marks = []
    if args.sanity:
        marks.append("sanity")
    if args.no_native or args.headless:
        marks.append("not native")
    if marks:
        pargs += ["-m", " and ".join(marks)]
    if args.reruns:
        pargs += ["--reruns", str(args.reruns)]
    pargs += extra
    print("pytest", " ".join(pargs))
    code = pytest.main(pargs)
    print(f"\nArtifacts: {run_dir}")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
