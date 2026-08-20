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
from ._cpp import (PLATFORM, conditional_spans, cpp_platform_state,
                   enclosing_conditions, line_of, mask_comments)

# const char kFoo[] = "foo";  /  inline constexpr char kFoo[] = "foo";
_STRING_CONST_RE = re.compile(
    r"\b(?:inline\s+)?(?:const|constexpr)\s+(?:constexpr\s+)?char\s+"
    r"(k\w+)\s*\[\s*\]\s*=\s*\"([^\"]*)\"\s*;"
)

# Chromium writes this filename both ways: `content_switches.cc` and, in a
# component that needs no prefix, plain `switches.cc`. Requiring the underscore
# read the first and silently skipped the second -- 44 files at M151, holding
# real switches like --headless, all of them fetched and none of them read.
_SWITCH_HINT = "switches."
# Two naming conventions carry pref keys, not one. `*pref_names.{h,cc}` is the
# older and larger set; `*_prefs.{h,cc}` is the newer one Chromium uses for
# per-component keys. Measured at M151, the second convention holds 469 keys in
# 54 files -- Memory Saver, Safety Hub, signin, enterprise connectors -- none of
# which this extractor read while it knew only the first.
_PREF_HINTS = ("pref_names.", "pref_names_", "_pref_names.",
               "_prefs.", "prefs.")


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
    # The build guard around a declaration, recorded for the same reason
    # base_features records it: a vendor fork does not edit upstream's key, it
    # puts its own beside it behind `#if defined(<VENDOR>_...)` and ships that
    # one. Both are present, so comparing values finds nothing -- the guard is
    # the whole evidence. Without it the shadow analysis could only ever see
    # base::Feature, which is 11% of the surface and none of the preference
    # keys the README calls the most expensive thing to get wrong.
    spans = conditional_spans(masked)
    facts: List[Fact] = []
    for m in _STRING_CONST_RE.finditer(masked):
        var, value = m.group(1), m.group(2)
        if not value:
            continue
        attrs = {"var": var}
        conditions = enclosing_conditions(spans, m.start())
        if conditions:
            attrs["conditions"] = conditions
            # Resolved for the platform we ship, and it is the resolution
            # rather than the raw guard that gets compared: upstream tidying
            # `!IS_ANDROID` off a key changes nothing about whether Windows has
            # it, and comparing the raw text reported 31 such moves at
            # M148 -> M151. What matters is a guard that takes the key out of
            # our binary, and that shows up here.
            state = cpp_platform_state(conditions)
            # Recorded only when the guard actually restricts us. "In our
            # binary" is the default, so a key with no guard and a key behind
            # `#if !BUILDFLAG(IS_ANDROID)` have to compare as the same thing --
            # otherwise upstream tidying a guard that never excluded Windows
            # reads as a change, which is 30 of them at M148 -> M151.
            if state and state != "compiled":
                attrs["platform_state"] = {PLATFORM: state}
        facts.append(Fact(
            kind=kind,
            key=value,
            name=value,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs=attrs,
        ))
    return facts
