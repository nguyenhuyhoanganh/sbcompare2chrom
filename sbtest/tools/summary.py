"""Print the result of the latest run: verdict, totals per feature, every failure with its
evidence, and where the report and the Confluence folder are.

    python -m sbtest.tools.summary               # artifacts/test-results
    python -m sbtest.tools.summary <run folder>
    python -m sbtest.tools.summary --json        # same data as JSON (for agents)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from sbtest.config import load_config
from sbtest.reporting.cases import load_cases
from sbtest.reporting.report import build_rows, summary


def collect(run_dir: Path) -> dict:
    path = run_dir / "results.json"
    if not path.exists():
        raise SystemExit(f"no results.json in {run_dir}: run the tests first (python run.py ...)")
    results = json.loads(path.read_text(encoding="utf-8"))
    rows = build_rows(results, load_cases())
    s = summary(rows, results["meta"])
    per_feature: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        per_feature[r.feature][r.result] += 1
    tests = {t["nodeid"]: t for t in results["tests"]}
    failures = [{"case": r.case_id, "title": r.title, "outcome": r.result, "test": r.test,
                 "failed_step": r.failed_step, "error": r.error,
                 "evidence": str(Path(tests[r.test]["evidence_dir"]) / "failure.txt") if tests[r.test].get("evidence_dir")
                 else ""}
                for r in rows if r.result in ("failed", "error")]
    starts = [(r["cases"][0] if r.get("cases") else r["name"], r["startup"]) for r in results["tests"] if r.get("startup")]
    startup = {}
    if starts:
        phases = sorted({k for _, t in starts for k in t})
        slowest = max(starts, key=lambda s: sum(s[1].values()))
        startup = {"browsers": len(starts),
                   "average": round(sum(sum(t.values()) for _, t in starts) / len(starts), 1),
                   "phases": {k: round(sum(t.get(k, 0) for _, t in starts) / len(starts), 1) for k in phases},
                   "slowest": {"case": slowest[0], "seconds": round(sum(slowest[1].values()), 1), **slowest[1]}}
    manifest = run_dir / "confluence" / "manifest.json"
    return {
        "build": s["build"], "selection": results["meta"].get("selection", ""), "verdict": f"BUILD {s['verdict']}",
        "totals": dict(s["counts"]), "per_feature": {f: dict(c) for f, c in per_feature.items()},
        "failures": failures,
        "skipped": [{"case": r.case_id, "reason": r.error} for r in rows if r.result == "skipped"],
        "startup": startup,
        "report": str(run_dir / "report" / "index.html"),
        "confluence": str(manifest.parent) if manifest.exists() else "",
        "confluence_title": json.loads(manifest.read_text(encoding="utf-8"))["title"] if manifest.exists() else "",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("run_dir", nargs="?", help="run folder (default: artifacts/test-results)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    data = collect(Path(args.run_dir) if args.run_dir else load_config().path("paths.results"))
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    order = ("passed", "failed", "error", "skipped")
    print(f"{data['verdict']}  {data['build']}  (selection: {data['selection']})")
    print("totals: " + ", ".join(f"{k} {data['totals'].get(k, 0)}" for k in order))
    for feature, c in data["per_feature"].items():
        print(f"  {feature:<10} " + "  ".join(f"{k} {c.get(k, 0)}" for k in order))
    for f in data["failures"]:
        print(f"\n{f['case']} [{f['outcome']}] {f['title']}\n  test:  {f['test']}")
        if f["failed_step"]:
            print(f"  step:  {f['failed_step']}")
        print(f"  error: {f['error']}")
        if f["evidence"]:
            print(f"  read:  {f['evidence']}")
    if data["skipped"]:
        print(f"\nskipped: {', '.join(s['case'] for s in data['skipped'])}")
    st = data["startup"]
    if st:
        phases = ", ".join(f"{k} {v}s" for k, v in st["phases"].items())
        print(f"\nbrowser start: {st['average']}s on average for {st['browsers']} start(s) ({phases}); "
              f"slowest {st['slowest']['case']} {st['slowest']['seconds']}s")
    print(f"\nreport:     {data['report']}")
    if data["confluence"]:
        print(f"confluence: {data['confluence']}  title: {data['confluence_title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
