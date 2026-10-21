"""Which test case ids (cases/**/*.md) are automated (@pytest.mark.case in tests/)?

    python -m sbtest.tools.coverage                 # table per feature
    python -m sbtest.tools.coverage --missing       # only ids without a test
    python -m sbtest.tools.coverage --feature bookmarks --json
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from sbtest.config import CASES_DIR, ROOT


def doc_cases(folder: Path = CASES_DIR) -> dict[str, dict]:
    """``{id: {title, feature, file, type, priority, ...}}`` from the markdown docs."""
    from sbtest.reporting.cases import load_cases

    return {cid: c.to_dict() for cid, c in load_cases(folder).items()}


def automated_cases(folder: Path = ROOT / "tests") -> dict[str, list[str]]:
    """``{id: ["tests/x.py::test_y", ...]}`` from @pytest.mark.case(...) decorators."""
    out: dict[str, list[str]] = {}
    for py in sorted(folder.rglob("test_*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "case"):
                    for a in dec.args:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            out.setdefault(a.value.upper(), []).append(f"{py.relative_to(ROOT).as_posix()}::{node.name}")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--feature")
    p.add_argument("--missing", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    docs, auto = doc_cases(), automated_cases()
    rows = []
    for cid, meta in sorted(docs.items()):
        if args.feature and meta["feature"] != args.feature:
            continue
        tests = auto.get(cid, [])
        if args.missing and tests:
            continue
        rows.append({"id": cid, **meta, "tests": tests})
    orphans = sorted(set(auto) - set(docs))
    if args.json:
        print(json.dumps({"cases": rows, "orphans": {o: auto[o] for o in orphans}}, indent=2))
        return 0
    feature = None
    for r in rows:
        if r["feature"] != feature:
            feature = r["feature"]
            done = sum(1 for x in rows if x["feature"] == feature and x["tests"])
            total = sum(1 for x in rows if x["feature"] == feature)
            print(f"\n== {feature or '(root)'}  {done}/{total} automated")
        mark = "OK " if r["tests"] else "-- "
        hint = f" [{r['type']}]" if r["type"] else ""
        print(f"  {mark}{r['id']:<9} {r['title'][:70]}{hint}")
        for t in r["tests"]:
            print(f"        {t}")
    if orphans:
        print("\nIds used in tests but missing in cases/: " + ", ".join(orphans))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
