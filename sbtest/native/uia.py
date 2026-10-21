"""Low level UIA helpers shared by the native layer: search, wait, read, dump."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from sbtest.utils import poll


def info(el) -> dict:
    ei = el.element_info
    try:
        r = el.rectangle()
        rect = (r.left, r.top, r.right, r.bottom)
    except Exception:  # noqa: BLE001
        rect = None
    return {
        "control_type": ei.control_type, "name": ei.name, "auto_id": ei.automation_id,
        "class_name": ei.class_name, "rect": rect,
    }


def matches(el, title: str | None = None, title_re: str | None = None, control_type: str | None = None,
            auto_id: str | None = None, class_name: str | None = None, class_name_re: str | None = None,
            **_ignored) -> bool:
    ei = el.element_info
    if control_type and ei.control_type != control_type:
        return False
    if auto_id and ei.automation_id != auto_id:
        return False
    if class_name and ei.class_name != class_name:
        return False
    if class_name_re and not re.search(class_name_re, ei.class_name or ""):
        return False
    if title is not None and (ei.name or "") != title:
        return False
    if title_re and not re.search(title_re, ei.name or ""):
        return False
    return True


# criteria UIA can evaluate natively (FindAll condition) - much faster than walking the
# whole tree in Python, which matters because web content adds thousands of nodes
_NATIVE_KEYS = ("control_type", "class_name", "title")


def descendants(root, **criteria) -> list:
    """``root`` and its descendants matching criteria (title/title_re/control_type/auto_id/
    class_name/class_name_re).
    ``found_index`` selects one of several matches."""
    idx = criteria.pop("found_index", None)
    native = {k: criteria[k] for k in _NATIVE_KEYS if criteria.get(k) is not None}
    try:
        items = [root] + root.descendants(**native)
    except Exception:  # noqa: BLE001 - window closed while walking, or condition unsupported
        try:
            items = [root] + root.descendants()
        except Exception:  # noqa: BLE001
            return []
    out = [e for e in items if matches(e, **criteria)]
    if idx is not None:
        return out[idx:idx + 1]
    return out


def find_in(roots: Iterable, timeout: float = 0, **criteria):
    """First matching element under any of ``roots`` (callable returning roots allowed)."""
    def _find():
        rs = roots() if callable(roots) else roots
        for r in rs:
            found = descendants(r, **dict(criteria))
            if found:
                return found[0]
        return None
    if timeout <= 0:
        return _find()
    return poll(_find, timeout, 0.3, f"UIA element {criteria}")


def texts(root, control_types=("Text", "Edit", "Button", "CheckBox", "ListItem", "MenuItem", "Hyperlink")) -> list[str]:
    """Readable strings in a window: names of text-like controls (plus Edit values)."""
    out = []
    for e in descendants(root):
        ct = e.element_info.control_type
        if ct not in control_types:
            continue
        name = e.element_info.name or ""
        if ct == "Edit":
            try:
                name = e.get_value() or name
            except Exception:  # noqa: BLE001
                pass
        if name.strip():
            out.append(name.strip())
    return out


def dump(root, max_depth: int = 25) -> str:
    """Indented tree: ``ControlType 'name' auto_id=.. class=.. rect=..`` (use to write criteria)."""
    lines: list[str] = []

    def walk(el, depth):
        i = info(el)
        lines.append("  " * depth + f"{i['control_type']} {i['name']!r} auto_id={i['auto_id']!r} "
                                    f"class={i['class_name']!r} rect={i['rect']}")
        if depth >= max_depth:
            return
        try:
            kids = el.children()
        except Exception:  # noqa: BLE001
            kids = []
        for k in kids:
            walk(k, depth + 1)

    walk(root, 0)
    return "\n".join(lines)


def dump_to(path: Path, roots: Iterable) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(dump(r) for r in roots), encoding="utf-8")
    return path
