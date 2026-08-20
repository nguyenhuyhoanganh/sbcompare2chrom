"""Extract ``base::Feature`` declarations and their default states.

Why this is the highest-value extractor: a base::Feature default flipping from
DISABLED to ENABLED is Chromium saying "this shipped".  That single bit
predicts most of the behaviour change a downstream browser inherits on an
uprev, and it is invisible in release notes.

Three declaration syntaxes coexist across the milestone range we care about:

    BASE_FEATURE(kFoo, "Foo", base::FEATURE_ENABLED_BY_DEFAULT);   // <= M141
    BASE_FEATURE(kFoo, base::FEATURE_ENABLED_BY_DEFAULT);          // >= M142
    const base::Feature kFoo{"Foo", base::FEATURE_DISABLED_BY_DEFAULT};  // legacy

The two-argument form derives the feature string from the variable name by
stripping the leading 'k'.  Normalizing to that string is what keeps identity
stable across the macro migration -- measured on content_features.cc, M139 has
170/170 declarations in the three-argument form and M143 has 12/187, so a
parser that keys on syntax reports the entire file as rewritten.
"""

from __future__ import annotations

import os
import re
from typing import List, Optional

from ..model import KIND_BASE_FEATURE, KIND_FEATURE_PARAM, Fact
from ._cpp import (
    balanced_args,
    collapse_ws,
    conditional_spans,
    enclosing_conditions,
    line_of,
    mask_comments,
    resolve_platform_state,
    split_top_level,
)

# Chromium's naming convention is strong but not a rule.  Measured at M151:
# in content/public/common the convention catches 201 of 201 declarations, but
# in chrome/browser/ui/webui it catches 1 of 24 -- the rest live in
# `_fieldtrial.cc`, `_util.cc` and `_handler.cc`.
#
# Widening the filter is free for correctness because the *download* list in
# targets.py already bounds what is on disk; this only decides what to read
# from it.
# Matched as substrings of the basename, so the bare spelling covers the
# prefixed one: "switches.cc" reads both `switches.cc` and
# `content_switches.cc`. They used to be spelled "_switches.cc", with the
# underscore required, which read the second and skipped the first.
FILE_HINTS = ("features.cc", "features.h",
              "switches.cc", "switches.h",
              "fieldtrial.cc", "fieldtrial.h",
              "field_trial.cc", "field_trial.h",
              "flags.cc", "flags.h",
              # Every other pair here covers both halves; this one covered only
              # the .cc, so a declaration in the header beside it was fetched
              # and then not read -- the quietest way to lose one.
              "feature_list.cc", "feature_list.h",
              "_util.cc", "_handler.cc", "_manager.cc")

# ...but widening pulls in test-only features, which are noise: a feature
# declared inside a browsertest exists to drive that test and ships to nobody.
# Of the 23 declarations the old filter missed in chrome/browser/ui/webui, 13
# were in test files.
TEST_FILE_HINTS = ("_unittest.", "_browsertest.", "_test.", "_testing.",
                   "test_util.", "_test_util.", "_test_helper.")

STATE_RE = re.compile(r"FEATURE_(ENABLED|DISABLED)_BY_DEFAULT")

_BASE_FEATURE_RE = re.compile(r"\bBASE_FEATURE\s*\(")
_LEGACY_FEATURE_RE = re.compile(
    r"\b(?:const\s+)?base::Feature\s+(k\w+)\s*\{", re.MULTILINE)
_FEATURE_PARAM_MACRO_RE = re.compile(r"\bBASE_FEATURE_PARAM\s*\(")
_FEATURE_PARAM_DECL_RE = re.compile(
    r"\bbase::FeatureParam\s*<\s*([^>]+?)\s*>\s*\n?\s*(k\w+)\s*\{", re.MULTILINE)

_STATE_MAP = {"ENABLED": "enabled", "DISABLED": "disabled"}


def applies_to(path: str) -> bool:
    base = os.path.basename(path)
    if not base.endswith((".cc", ".h")):
        return False
    if any(h in base for h in TEST_FILE_HINTS):
        return False
    return any(h in base for h in FILE_HINTS)


def feature_name_from_var(var: str) -> str:
    """kBackForwardCache -> BackForwardCache (Chromium's own convention).

    The single definition, imported by every stage that has to get from a C++
    identifier back to the feature string a fact is keyed on: the reference
    closure in `catalog`, the clustering in `cluster`, and area routing in
    `sbprofile`. It is applied here first, to derive the key from the
    two-argument macro form, so a copy elsewhere that drifted would silently
    stop matching the keys this produces.
    """
    if len(var) > 1 and var[0] == "k" and var[1].isupper():
        return var[1:]
    return var


def _normalize_state(token: str) -> str:
    m = STATE_RE.search(token)
    if not m:
        return "unknown"
    return _STATE_MAP.get(m.group(1), "unknown")


def _platform_states(block: str) -> dict:
    raw = resolve_platform_state(block, STATE_RE)
    return {k: _normalize_state(v) if v.startswith("FEATURE_") else v
            for k, v in raw.items()}


def extract(text: str, rel_path: str) -> List[Fact]:
    """Parse one C++ source file into base_feature / feature_param facts."""
    masked = mask_comments(text)
    # A vendor fork adds its code beside upstream's and picks between them with
    # a build flag, so the guard around a declaration is as informative as the
    # declaration. Without it, a feature the vendor has quietly shadowed reads
    # as identical to upstream.
    spans = conditional_spans(masked)
    facts: List[Fact] = []

    facts.extend(_extract_base_feature_macro(masked, rel_path, spans))
    facts.extend(_extract_legacy_feature(masked, rel_path, spans))
    facts.extend(_extract_feature_params(masked, rel_path))
    return facts


# ---------------------------------------------------------------------------


def _extract_base_feature_macro(masked: str, rel_path: str,
                                spans=()) -> List[Fact]:
    facts: List[Fact] = []
    for m in _BASE_FEATURE_RE.finditer(masked):
        open_idx = masked.index("(", m.start())
        try:
            inner, _ = balanced_args(masked, open_idx)
        except ValueError:
            continue
        args = split_top_level(inner)
        if not args or not args[0]:
            continue
        var = args[0].strip()
        if not re.match(r"^k\w+$", var):
            continue

        name: Optional[str] = None
        if len(args) >= 3:
            sm = re.match(r'^"([^"]+)"$', args[1].strip())
            if sm:
                name = sm.group(1)
        if name is None:
            name = feature_name_from_var(var)

        state = _normalize_state(inner)
        facts.append(Fact(
            kind=KIND_BASE_FEATURE,
            key=name,
            name=name,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={
                "var": var,
                "default_state": state,
                "platform_state": _platform_states(inner),
                "declared_form": "macro3" if len(args) >= 3 else "macro2",
                "conditions": enclosing_conditions(list(spans), m.start()),
            },
        ))
    return facts


def _extract_legacy_feature(masked: str, rel_path: str, spans=()) -> List[Fact]:
    """The pre-macro declaration form, which must produce the same shape.

    Every attribute the diff compares has to be present in both forms or the
    comparison invents a change. Omitting ``conditions`` here meant a feature
    written the old way on one side and the macro way on the other reported as
    modified with `conditions: None -> [...]` even when the guard, the state and
    the name were identical. Rare across two Chromium releases; not rare at all
    against a vendor fork, where old declaration styles survive for years.
    """
    facts: List[Fact] = []
    for m in _LEGACY_FEATURE_RE.finditer(masked):
        var = m.group(1)
        brace = masked.index("{", m.start())
        end = masked.find("}", brace)
        if end == -1:
            continue
        inner = masked[brace + 1 : end]
        args = split_top_level(inner)
        name = None
        if args:
            sm = re.match(r'^"([^"]+)"$', args[0].strip())
            if sm:
                name = sm.group(1)
        name = name or feature_name_from_var(var)
        facts.append(Fact(
            kind=KIND_BASE_FEATURE,
            key=name,
            name=name,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={
                "var": var,
                "default_state": _normalize_state(inner),
                "platform_state": _platform_states(inner),
                "declared_form": "legacy",
                "conditions": enclosing_conditions(list(spans), m.start()),
            },
        ))
    return facts


def _extract_feature_params(masked: str, rel_path: str) -> List[Fact]:
    """FeatureParams are tuning knobs; a changed default changes behaviour.

    Both the brace-initializer form and the newer BASE_FEATURE_PARAM macro are
    handled.  The owning feature is recorded so a param change can be reported
    next to the feature it belongs to.
    """
    facts: List[Fact] = []

    for m in _FEATURE_PARAM_DECL_RE.finditer(masked):
        ptype, var = m.group(1), m.group(2)
        brace = masked.index("{", m.end() - 1)
        end = _find_close_brace(masked, brace)
        if end is None:
            continue
        args = split_top_level(masked[brace + 1 : end])
        facts.append(_param_fact(args, ptype, var, rel_path,
                                 line_of(masked, m.start()), owner_first=True))

    for m in _FEATURE_PARAM_MACRO_RE.finditer(masked):
        open_idx = masked.index("(", m.start())
        try:
            inner, _ = balanced_args(masked, open_idx)
        except ValueError:
            continue
        args = split_top_level(inner)
        if len(args) < 4:
            continue
        ptype, var = args[0], args[1]
        facts.append(_param_fact(args[2:], ptype, var, rel_path,
                                 line_of(masked, m.start()), owner_first=True))

    return [f for f in facts if f is not None]


def _param_fact(args, ptype, var, rel_path, line, owner_first=True) -> Optional[Fact]:
    owner = ""
    pname = ""
    default = ""
    if args:
        first = args[0].strip()
        if first.startswith("&"):
            owner = feature_name_from_var(first.lstrip("&").split("::")[-1])
            rest = args[1:]
        else:
            rest = args
        if rest:
            nm = re.match(r'^"([^"]*)"$', rest[0].strip())
            pname = nm.group(1) if nm else rest[0].strip()
        if len(rest) > 1:
            default = collapse_ws(rest[1])
    if not pname:
        return None
    key = f"{owner}/{pname}" if owner else f"{rel_path}:{pname}"
    return Fact(
        kind=KIND_FEATURE_PARAM,
        key=key,
        name=pname,
        path=rel_path,
        line=line,
        attrs={
            "feature": owner,
            "type": collapse_ws(ptype),
            "var": var,
            "default": default,
        },
    )


def _find_close_brace(text: str, open_idx: int) -> Optional[int]:
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None
