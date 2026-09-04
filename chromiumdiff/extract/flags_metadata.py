"""Extract chrome://flags metadata (expiry milestones).

``chrome/browser/flag-metadata.json`` records, for every chrome://flags entry,
the milestone at which it is scheduled for removal.  That makes it the only
source in the tree that is explicitly *about the future*: it tells a team
which flags will disappear in the milestone after the one they are landing.

This converts a class of surprise breakage into
planned work -- "these 12 flags we depend on expire in M148" is a backlog item
you can file today rather than a build failure you discover next upgrade.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List

from .. import jsonc
from ..model import KIND_FLAG_ENTRY, Fact

FILENAME = "flag-metadata.json"


def applies_to(path: str) -> bool:
    return os.path.basename(path) == FILENAME


# Same reason as blink_runtime: the parse yields values, not positions, and a
# chrome://flags entry with no line is a citation nobody can follow into a
# 20,000-line manifest.
# The `{` may share the line, as it does for two entries at M151.
# `[ \t]` rather than `\s`, which matches newlines: with `\s*` the pattern
# reached across the line holding `{` and reported that one instead.
_NAME_LINE_RE = re.compile(
    r'^[ \t]*\{?[ \t]*"name"[ \t]*:[ \t]*"([^"]+)"', re.MULTILINE)


def name_lines(text: str) -> Dict[str, int]:
    return {m.group(1): text.count("\n", 0, m.start()) + 1
            for m in _NAME_LINE_RE.finditer(text)}


def extract(text: str, rel_path: str) -> List[Fact]:
    try:
        doc = jsonc.loads(text)
    except jsonc.Json5Error:
        return []
    if not isinstance(doc, list):
        return []
    lines = name_lines(text)
    facts: List[Fact] = []
    for entry in doc:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        facts.append(Fact(
            kind=KIND_FLAG_ENTRY,
            key=name,
            name=name,
            path=rel_path,
            line=lines.get(name, 0),
            attrs={
                "expiry_milestone": entry.get("expiry_milestone"),
                "owners": entry.get("owners", []),
            },
        ))
    return facts
