"""Extract the page inventory of a desktop WebUI surface from its route table.

``chrome://settings``, ``chrome://history``, ``chrome://downloads``,
``chrome://bookmarks``, ``chrome://extensions`` and roughly 130 other
``chrome://`` pages are all web pages under ``chrome/browser/resources/``. The
ones with sub-navigation declare it in a route table, which is the surface's
table of contents. Settings has 104 routes at M148 and 108 at M151.

The critical part is not the list but the **guard**. Routes are declared inside
``if (loadTimeData.getBoolean('someKey'))`` blocks, and that key is set from
C++ based on a feature flag. A route present in the file may never render.

At M148 both of these were declared at once, mid-migration::

    if (loadTimeData.getBoolean('enableLocalNetworkAccessSetting')) {
      r.SITE_SETTINGS_LOCAL_NETWORK_ACCESS = r.SITE_SETTINGS.createChild('localNetworkAccess');
    }
    if (loadTimeData.getBoolean('enableLocalNetworkAccessSplitPermissions')) {
      r.SITE_SETTINGS_LOCAL_NETWORK = r.SITE_SETTINGS.createChild('localNetwork');
    }

Reading the list alone says "a page disappeared in M151". Reading the guard,
and following it to its flag, says what actually happened: the old page was
already hidden at M148 because the split-permissions flag was on. The guard is
therefore captured as an attribute, and the diff compares it.
"""

from __future__ import annotations

import os
import re
from typing import List

from ..model import KIND_WEBUI_ROUTE, Fact
from ._cpp import collapse_ws, line_of, mask_comments
from .webui_controls import RESOURCES_DIR, surface_of

ROUTE_FILENAMES = ("route.ts", "routes.ts")

# r.NAME = r.PARENT.createChild('/path')   |   .createSection('/path', 'name')
_ROUTE_RE = re.compile(
    r"\b\w+\.([A-Z][A-Z0-9_]*)\s*=\s*"
    r"(?:\w+\.([A-Z][A-Z0-9_]*)\.)?"
    r"create(Child|Section)\(\s*['\"]([^'\"]+)['\"]"
)

_GUARD_KEY_RE = re.compile(r"loadTimeData\.getBoolean\(\s*['\"](\w+)['\"]")


def applies_to(path: str) -> bool:
    return (path.startswith(RESOURCES_DIR)
            and os.path.basename(path) in ROUTE_FILENAMES)


def _guard_stack_at(text: str, index: int) -> List[str]:
    """Which loadTimeData keys guard the code at ``index``.

    Tracks brace depth rather than parsing TypeScript: a guard applies from its
    opening brace until the matching close. Sufficient because route tables are
    flat, generated-looking code with no closures inside guarded blocks.
    """
    stack: List[tuple] = []   # (depth_at_open, key)
    depth = 0
    i = 0
    quote = ""
    while i < index and i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = ""
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            while stack and stack[-1][0] > depth:
                stack.pop()
        elif c == "i" and text.startswith("if", i):
            end = text.find("\n", i)
            end = len(text) if end == -1 else end
            head = text[i:end]
            m = _GUARD_KEY_RE.search(head)
            if m and "{" in head:
                stack.append((depth + 1, m.group(1)))
        i += 1
    return [key for _, key in stack]


def extract(text: str, rel_path: str) -> List[Fact]:
    masked = mask_comments(text)
    surface = surface_of(rel_path)
    facts: List[Fact] = []
    for m in _ROUTE_RE.finditer(masked):
        name, parent, route_kind, route = (
            m.group(1), m.group(2) or "", m.group(3), m.group(4))
        facts.append(Fact(
            kind=KIND_WEBUI_ROUTE,
            key=f"{surface}/{name}",
            name=name,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={
                "surface": surface,
                "route": route,
                "parent": parent,
                "route_kind": collapse_ws(route_kind).lower(),
                # Empty means unconditional. A guard here is the link to the
                # flag that decides whether users ever see this page.
                "guards": _guard_stack_at(masked, m.start()),
            },
        ))
    return facts
