"""(Re)build the sanity report of a run: HTML + Markdown + Confluence-ready folder.

    python -m sbtest.tools.report                       # latest run in artifacts/runs/
    python -m sbtest.tools.report artifacts/runs/<ts>   # a given run
    python -m sbtest.tools.report --open                # and open index.html

Runs write these automatically at the end; use this after editing testcases/*.md (the
report takes names, steps and expected results from there) or to rebuild an old run.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from sbtest.config import ROOT
from sbtest.reporting.confluence_export import export
from sbtest.reporting.report import generate


def latest_run() -> Path:
    runs = sorted((p for p in (ROOT / "artifacts" / "runs").glob("*") if (p / "results.json").exists()),
                  key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("no run with results.json in artifacts/runs/")
    return runs[-1]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("run_dir", nargs="?", help="artifacts/runs/<ts> (default: latest)")
    p.add_argument("--open", action="store_true", help="open the HTML report")
    args = p.parse_args(argv)
    run_dir = Path(args.run_dir) if args.run_dir else latest_run()
    index = generate(run_dir)
    conf = export(run_dir)
    print(f"Report:     {index}")
    print(f"Confluence: {conf}  (create the page with the Confluence skill, see sbtest-run)")
    if args.open and os.name == "nt":
        os.startfile(index)  # noqa: S606 - local file
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
