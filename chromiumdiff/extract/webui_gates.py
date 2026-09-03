"""Extract the bridge between a WebUI page and the feature flags behind it.

A WebUI page asks ``loadTimeData.getBoolean('someKey')`` to decide what to
show. The C++ handler decides what that key holds, and it usually reduces to
one or more ``base::Feature`` checks. This extractor captures that link, which
is the middle hop of::

    route table  --guard-->  loadTimeData key  --here-->  base::Feature

Without it, a page appearing or disappearing in the route table cannot be
explained, and the reader is left with the wrong conclusion.

The real M148 declaration shows why the *expression* matters, not just the
feature list::

    html_source->AddBoolean(
        "enableLocalNetworkAccessSetting",
        base::FeatureList::IsEnabled(network::features::kLocalNetworkAccessChecks) &&
            !network::features::kLocalNetworkAccessChecksWarn.Get() &&
            !base::FeatureList::IsEnabled(
                network::features::kLocalNetworkAccessChecksSplitPermissions));

Both the old and the new Local Network Access page depend on the same three
flags; the only difference is that the old one requires SplitPermissions to be
*off*. Since that flag was enabled by default at M148, the old page was already
invisible before the version that deleted it.
"""

from __future__ import annotations

import re
from typing import List

from ..model import KIND_WEBUI_GATE, Fact
from ._cpp import balanced_args, collapse_ws, line_of, mask_comments, split_top_level

WEBUI_HANDLER_DIR = "chrome/browser/ui/webui/"

# html_source->AddBoolean("key", <expression>) and its Add* siblings.
_ADD_RE = re.compile(r"\bAdd(Boolean|Integer|String|Double)\s*\(")

# network::features::kFoo | features::kFoo | blink::features::kBar
_FEATURE_REF_RE = re.compile(r"(?:(\w+)::)?features::(k\w+)")
_ISENABLED_RE = re.compile(r"IsEnabled\s*\(\s*(?:\w+::)*features::(k\w+)")


def applies_to(path: str) -> bool:
    return path.startswith(WEBUI_HANDLER_DIR) and path.endswith(".cc")


def _handler_of(rel_path: str) -> str:
    """downloads/downloads_ui.cc -> downloads_ui"""
    name = rel_path.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".cc") else name


def _features_in(expr: str) -> List[str]:
    """Every base::Feature named anywhere in the expression, in order."""
    seen: List[str] = []
    for m in _FEATURE_REF_RE.finditer(expr):
        name = m.group(2)
        if name not in seen:
            seen.append(name)
    return seen


def extract(text: str, rel_path: str) -> List[Fact]:
    masked = mask_comments(text)
    facts: List[Fact] = []

    for m in _ADD_RE.finditer(masked):
        open_idx = masked.index("(", m.start())
        try:
            inner, _ = balanced_args(masked, open_idx)
        except ValueError:
            continue
        args = split_top_level(inner)
        if len(args) < 2:
            continue
        key_match = re.match(r'^"([\w.-]+)"$', args[0].strip())
        if not key_match:
            continue
        key = key_match.group(1)
        expr = collapse_ws(",".join(args[1:]))

        features = _features_in(expr)
        # A gate with no feature reference is a runtime/profile condition
        # (guest session, enterprise policy). Still worth recording -- it is
        # a visibility decision -- but it will not join to a flag.
        # The loadTimeData key alone is not unique: 62 of 668 at M151 are set
        # by more than one handler, 27 of them to different expressions --
        # `undoDescription` by both bookmarks_ui.cc and downloads_ui.cc. Keyed
        # on the string alone, one of each pair was dropped as a duplicate and
        # which one depended on directory walk order, exactly the defect the
        # WebUI *control* identity was qualified to fix two schema versions
        # ago. Qualifying by handler recovers 96 declarations for 5 extra
        # removals where a handler file was renamed.
        #
        # `data_key` keeps the bare string, because that is what a route names
        # and what the reference closure resolves against.
        facts.append(Fact(
            kind=KIND_WEBUI_GATE,
            key=f"{_handler_of(rel_path)}/{key}",
            name=key,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={
                "data_key": key,
                "handler": _handler_of(rel_path),
                "value_type": m.group(1).lower(),
                "expression": expr[:400],
                "features": features,
                "enabled_checks": sorted(set(_ISENABLED_RE.findall(expr))),
            },
        ))
    return facts
