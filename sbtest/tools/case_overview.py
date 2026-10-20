"""Regenerate testcases/TESTCASES.md: every case with its target, sanity flag and the latest
result on each target, plus the full steps / expected of each case.

    python -m sbtest.tools.case_overview                     # latest run per target from artifacts/runs/
    python -m sbtest.tools.case_overview --no-results        # cases only

A result is taken from the most recent run of that target that executed the case.
"""
from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

from sbtest.config import ROOT
from sbtest.reporting.cases import load_cases

FEATURES = [("addons", "Add-ons", "ADD"), ("bookmarks", "Bookmarks", "BM"), ("downloads", "Downloads", "DL"),
            ("history", "History", "HIS"), ("settings", "Settings", "SET"), ("general", "General", "GEN")]
TARGET_LABEL = {"both": "Cả hai", "samsung": "Samsung", "chrome": "Chrome"}
STATUS = {"passed": "✅ Pass", "failed": "❌ Fail", "error": "❌ Error", "skipped": "⏭ Skip", "na": "N/A", None: "⏳ Chưa chạy"}


def test_markers(folder: Path = ROOT / "tests" / "features") -> dict[str, dict]:
    """``{case_id: {"target": both|samsung|chrome, "sanity": bool}}`` from decorators + pytestmark."""
    out: dict[str, dict] = {}

    def marks_of(nodes) -> tuple[set[str], set[str]]:
        names, targets = set(), set()
        for n in ast.walk(nodes) if not isinstance(nodes, list) else [x for node in nodes for x in ast.walk(node)]:
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and n.value.attr == "mark":
                names.add(n.attr)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "targets":
                targets |= {a.value for a in n.args if isinstance(a, ast.Constant)}
        return names, targets

    for py in folder.rglob("test_*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        aliases: dict[str, ast.AST] = {}
        module_marks: list[ast.AST] = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == "pytestmark":
                    module_marks.append(node.value)
                else:
                    aliases[node.targets[0].id] = node.value
        _, module_targets = marks_of(module_marks)
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            decos = [aliases.get(d.id, d) if isinstance(d, ast.Name) else d for d in fn.decorator_list]
            names, targets = marks_of(decos)
            ids = [a.value for d in fn.decorator_list if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                   and d.func.attr == "case" for a in d.args if isinstance(a, ast.Constant)]
            tgt = targets or module_targets
            for cid in ids:
                out[cid] = {"target": next(iter(tgt)) if len(tgt) == 1 else "both", "sanity": "sanity" in names}
    return out


def latest_results() -> dict[str, dict[str, str]]:
    """``{target: {case_id: outcome}}``, newest run wins per case."""
    runs = sorted((p for p in (ROOT / "artifacts" / "runs").glob("*/results.json")), key=lambda p: p.stat().st_mtime)
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for path in runs:
        data = json.loads(path.read_text(encoding="utf-8"))
        target = data["meta"].get("target", "")
        for t in data["tests"]:
            outcome = t["outcome"]
            if outcome == "skipped" and "not applicable to target" in (t.get("message") or ""):
                outcome = "na"
            for cid in t.get("cases") or []:
                out[target][cid] = outcome
    return out


def render(results: dict[str, dict[str, str]] | None) -> str:
    cases = load_cases()
    marks = test_markers()
    by_feature = defaultdict(list)
    for c in cases.values():
        by_feature[c.feature].append(c)
    L: list[str] = []
    w = L.append
    total = len(cases)
    native = sum(c.type.startswith("native") for c in cases.values())
    w("# Danh sách test case - sbtest")
    w("")
    w("File sinh tự động bởi `python -m sbtest.tools.case_overview` từ `testcases/**/*.md` và marker của test.")
    w("Đừng sửa tay: sửa file case gốc rồi chạy lại lệnh. Nội dung case giữ nguyên tiếng Anh như file gốc.")
    w("")
    w(f"**{total} test case**, tất cả đã có script tự động ({total - native} web, {native} native).")
    w("")
    w("| Feature | Prefix | Số case | Web | Native | Sanity | Cả hai target | Chỉ Samsung | Chỉ Chrome |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    tot = Counter()
    for key, name, prefix in FEATURES:
        cs = by_feature.get(key, [])
        t = Counter(marks.get(c.id, {}).get("target", "both") for c in cs)
        row = [len(cs), sum(not c.type.startswith("native") for c in cs), sum(c.type.startswith("native") for c in cs),
               sum(marks.get(c.id, {}).get("sanity", False) for c in cs), t["both"], t["samsung"], t["chrome"]]
        tot.update(dict(enumerate(row)))
        w(f"| {name} | {prefix} | " + " | ".join(str(x) for x in row) + " |")
    w("| **Tổng** | | " + " | ".join(f"**{tot[i]}**" for i in range(7)) + " |")
    w("")
    w("- **Type** `web`: chỉ nội dung trang (Selenium); `native`: có UI của browser / dialog Windows (pywinauto).")
    w("- **Target** `Cả hai`: cùng test chạy trên Samsung và Chrome; `Samsung`/`Chrome`: luồng chỉ một bên có.")
    w("- **Sanity**: thuộc lượt kiểm tra nhanh (`python run.py --sanity`).")
    if results is not None:
        w("- **Samsung / Chrome**: kết quả gần nhất trong `artifacts/runs/` của máy sinh file này.")
    w("")
    w("Chạy theo feature: `python run.py --feature bookmarks` · theo case: `python run.py --case BM-101,DL-104`.")
    w("")
    for key, name, prefix in FEATURES:
        cs = sorted(by_feature.get(key, []), key=lambda c: (c.id.split("-")[0], int(c.id.split("-")[-1])))
        if not cs:
            continue
        w(f"## {name} ({prefix}) - {len(cs)} case")
        w("")
        head = "| ID | Tên | Ưu tiên | Type | Target | Sanity | File |" + (" Samsung | Chrome |" if results is not None else "")
        w(head)
        w("|" + "---|" * (head.count("|") - 1))
        for c in cs:
            m = marks.get(c.id, {"target": "both", "sanity": False})
            cells = [c.id, c.title, c.priority or "-", (c.type.split() or ["-"])[0], TARGET_LABEL[m["target"]],
                     "✔" if m["sanity"] else "", Path(c.file).name]
            if results is not None:
                for tgt in ("samsung", "chrome"):
                    applies = m["target"] in ("both", tgt)
                    cells.append(STATUS[results.get(tgt, {}).get(c.id)] if applies else "N/A")
            w("| " + " | ".join(x.replace("|", "\\|") for x in cells) + " |")
        w("")
        for c in cs:
            w(f"<details><summary><b>{c.id}</b> {c.title}</summary>")
            w("")
            if c.precondition:
                w(f"**Precondition:** {c.precondition}")
                w("")
            if c.steps:
                w("**Steps:**")
                w("")
                w("\n".join(f"{i}. {s}" for i, s in enumerate(c.steps, 1)))
                w("")
            if c.expected:
                w("**Expected:**")
                w("")
                w("\n".join(f"- {e}" for e in c.expected))
                w("")
            w(f"**Nguồn:** `{c.file}`  ")
            w(f"**Script:** `{c.automated}`")
            w("")
            w("</details>")
            w("")
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--no-results", action="store_true", help="leave out the per-target result columns")
    p.add_argument("--out", default=str(ROOT / "testcases" / "TESTCASES.md"))
    args = p.parse_args(argv)
    text = render(None if args.no_results else latest_results())
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"{args.out} ({len(load_cases())} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
