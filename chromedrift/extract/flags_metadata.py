"""Extract chrome://flags metadata (expiry milestones).

``chrome/browser/flag-metadata.json`` records, for every chrome://flags entry,
the milestone at which it is scheduled for removal.  That makes it the only
source in the tree that is explicitly *about the future*: it tells a team
which flags will disappear in the milestone after the one they are landing.

For a downstream browser this converts a class of surprise breakage into
planned work -- "these 12 flags we depend on expire in M148" is a backlog item
you can file today rather than a build failure you discover next uprev.
"""

from __future__ import annotations

import os
from typing import List

from .. import jsonc
from ..model import KIND_FLAG_ENTRY, Fact

FILENAME = "flag-metadata.json"


def applies_to(path: str) -> bool:
    return os.path.basename(path) == FILENAME


def extract(text: str, rel_path: str) -> List[Fact]:
    try:
        doc = jsonc.loads(text)
    except jsonc.Json5Error:
        return []
    if not isinstance(doc, list):
        return []
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
            attrs={
                "expiry_milestone": entry.get("expiry_milestone"),
                "owners": entry.get("owners", []),
            },
        ))
    return facts
