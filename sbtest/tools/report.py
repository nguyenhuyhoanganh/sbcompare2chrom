"""(Re)build the sanity report of a run: HTML + Markdown + Confluence-ready folder.

    python -m sbtest.tools.report                       # the run in artifacts/test-results/
    python -m sbtest.tools.report <folder>              # a copied run folder
    python -m sbtest.tools.report --open                # and open index.html

Runs write these automatically at the end; use this after editing the case docs (*.md) (the
report takes names, steps and expected results from there).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from sbtest.config import load_config
from sbtest.reporting.confluence_export import export
from sbtest.reporting.report import generate


def latest_run() -> Path:
    run_dir = load_config().path("paths.results")
    if not (run_dir / "results.json").exists():
        raise SystemExit(f"no results.json in {run_dir}: run the tests first")
    return run_dir


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("run_dir", nargs="?", help="run folder (default: artifacts/test-results)")
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
