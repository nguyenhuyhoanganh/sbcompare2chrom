"""Read the normalized test case documents (cases/<feature>/*.md).

    cases = load_cases()            # {"BM-101": Case(...), ...}
    cases["BM-101"].steps           # ["Open 'Static page 1'", "Press Ctrl+D", ...]

Format of a case (see cases/README.md)::

    ## BM-101 Title
    - Priority: High
    - Type: native
    - Precondition: ...
    - Steps:
      1. ...
    - Expected:
      - ...
    - Automated: tests/features/...::test_x
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sbtest.config import CASES_DIR, ROOT

CASE_HEADER = re.compile(r"^#{2,3}\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+)\b\s*(.*)$")  # BM-001, SI-ADD-012
FIELD = re.compile(r"^-\s*(Priority|Type|Precondition|Steps|Expected|Automated)\s*:\s*(.*)$", re.I)


@dataclass
class Case:
    id: str
    title: str
    feature: str
    file: str
    priority: str = ""
    type: str = ""
    precondition: str = ""
    steps: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    automated: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def parse_file(md: Path, feature: str, rel: str) -> list[Case]:
    out: list[Case] = []
    current: Case | None = None
    section = ""
    for raw in md.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        m = CASE_HEADER.match(line.strip())
        if m:
            current = Case(m.group(1), m.group(2).strip(), feature, rel)
            out.append(current)
            section = ""
            continue
        if current is None or not line.strip():
            continue
        if line.startswith("#"):          # a non-case heading ends the case
            current, section = None, ""
            continue
        f = FIELD.match(line.strip()) if not line.startswith("  ") else None
        if f:
            key, value = f.group(1).lower(), f.group(2).strip()
            section = key
            if key in ("steps", "expected"):
                if value:
                    getattr(current, key).append(value)
            else:
                setattr(current, key, value)
            continue
        item = re.match(r"^\s+(?:\d+[.)]|-)\s+(.*)$", line)
        if item and section in ("steps", "expected"):
            getattr(current, section).append(item.group(1).strip())
        elif section in ("steps", "expected") and getattr(current, section):
            getattr(current, section)[-1] += " " + line.strip()   # wrapped line
        elif section == "precondition":
            current.precondition += " " + line.strip()
    return out


def load_cases(folder: Path = CASES_DIR) -> dict[str, Case]:
    out: dict[str, Case] = {}
    for md in sorted(folder.rglob("*.md")):
        rel_parts = md.relative_to(folder).parts
        if md.name.lower() in ("readme.md", "cases.md") or "_inbox" in rel_parts:
            continue  # _inbox = raw Confluence/Jira copies; TESTCASES.md = generated overview
        feature = rel_parts[0] if len(rel_parts) > 1 else ""
        for case in parse_file(md, feature, str(md.relative_to(ROOT)).replace("\\", "/")):
            out[case.id] = case
    return out
