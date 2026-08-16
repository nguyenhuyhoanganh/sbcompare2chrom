"""Extract command-line switches and preference keys.

Both are plain string constants, and both are *contracts with things outside
the browser binary*: launch scripts, automation harnesses, device policy,
settings UI and stored user profiles.

That external-contract property is why a removed switch or renamed pref path
deserves attention out of proportion to its diff size.  A renamed pref key
silently orphans every existing user's stored value -- the code still compiles
and the tests still pass, and the setting quietly resets in the field.
"""

from __future__ import annotations

import os
import re
from typing import List

from ..model import KIND_PREF, KIND_SWITCH, Fact
from ._cpp import line_of, mask_comments

# const char kFoo[] = "foo";  /  inline constexpr char kFoo[] = "foo";
_STRING_CONST_RE = re.compile(
    r"\b(?:inline\s+)?(?:const|constexpr)\s+(?:constexpr\s+)?char\s+"
    r"(k\w+)\s*\[\s*\]\s*=\s*\"([^\"]*)\"\s*;"
)

_SWITCH_HINT = "_switches."
_PREF_HINTS = ("pref_names.", "pref_names_", "_pref_names.")


def applies_to(path: str) -> bool:
    base = os.path.basename(path)
    if not base.endswith((".cc", ".h")):
        return False
    return _SWITCH_HINT in base or any(h in base for h in _PREF_HINTS)


def _kind_for(path: str) -> str:
    base = os.path.basename(path)
    if any(h in base for h in _PREF_HINTS):
        return KIND_PREF
    return KIND_SWITCH


def extract(text: str, rel_path: str) -> List[Fact]:
    kind = _kind_for(rel_path)
    masked = mask_comments(text)
    facts: List[Fact] = []
    for m in _STRING_CONST_RE.finditer(masked):
        var, value = m.group(1), m.group(2)
        if not value:
            continue
        facts.append(Fact(
            kind=kind,
            key=value,
            name=value,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={"var": var},
        ))
    return facts
