"""Prepare a run for Confluence: python -m sbtest.tools.confluence_export artifacts/test-results

Writes <run_dir>/confluence/ (manifest.json, page.storage.html, page.md, attachments/).
Then use the Confluence skill to create a page from it and upload the attachments.
run.py does this automatically after every run.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sbtest.reporting.confluence_export import export


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("run_dir")
    out = export(Path(p.parse_args(argv).run_dir))
    print(f"Confluence export: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
