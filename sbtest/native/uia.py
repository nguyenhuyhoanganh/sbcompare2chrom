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
    # "^(A|B)$" (a class renamed between builds) -> one native search per class name, not
    # a walk over the whole tree (web content has thousands of nodes)
    names = re.fullmatch(r"\^\(?([\w|]+)\)?\$", criteria.get("class_name_re") or "")
    queries = [{**native, "class_name": n} for n in names.group(1).split("|")] if names and not native.get(
        "class_name") else [native]
    try:
        items = [root] + [e for q in queries for e in root.descendants(**q)]
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


def _rect(el) -> tuple[int, int, int, int]:
    r = el.rectangle()
    return (r.left, r.top, r.right, r.bottom)


def wait_actionable(el, timeout: float = 5, interval: float = 0.1):
    """Wait until ``el`` can take a click like a user would: enabled, on screen, with a size,
    and at the same place on two checks in a row (menus, bubbles and panels slide or grow
    while they open, so a click aimed at a moving rectangle lands next to the button).
    Returns ``el``; raises TimeoutError saying which condition never held."""
    state = {"rect": None, "why": "not checked yet"}

    def _ready():
        if not el.is_enabled():
            state["why"] = "disabled"
            return False
        if not el.is_visible():
            state["why"] = "off screen / hidden"
            return False
        rect = _rect(el)
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            state["why"] = f"no size {rect}"
            return False
        moved, state["rect"] = rect != state["rect"], rect
        if moved:
            state["why"] = f"still moving (now at {rect})"
            return False
        return True

    name = f"{el.element_info.control_type} {el.element_info.name!r}"
    try:
        poll(_ready, timeout, interval, f"{name} ready to click")
    except TimeoutError as e:
        raise TimeoutError(f"{name} not ready to click after {timeout}s: {state['why']}") from e
    return el


def input_protection() -> float:
    """Seconds a Chromium dialog/bubble ignores clicks after it is shown.

    Chromium drops clicks on dialog buttons that come sooner than the double-click time after
    the dialog appears (InputEventActivationProtector, against clicks meant for the page
    below), so a click on a just-opened bubble does nothing. Windows setting + margin."""
    try:
        import ctypes

        return ctypes.windll.user32.GetDoubleClickTime() / 1000 + 0.1
    except Exception:  # noqa: BLE001 - not Windows
        return 0.6


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
