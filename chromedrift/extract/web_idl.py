"""Extract the Web IDL surface: interfaces and their members.

IDL is where "a new web API landed" becomes concrete and testable.  Diffing it
answers three distinct questions an uprev raises:

  * added member   -> new surface to test, and possibly to adopt in the UI
  * removed member -> a site-visible compatibility break
  * changed signature / extended attributes -> silent behaviour change

The ``[RuntimeEnabled=Foo]`` extended attribute is the join key back to
`runtime_enabled_features.json5`, which is how a member can be reported
together with the flag that gates it.

This is a pragmatic lexer, not a spec-complete WebIDL parser: it recognises
the definition and member forms Chromium actually uses and skips anything it
does not understand rather than failing the file.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..model import KIND_IDL_INTERFACE, KIND_IDL_MEMBER, Fact
from ._cpp import (collapse_ws, line_of, mask_comments, split_top_level,
                   split_top_level_offsets)

_DEF_RE = re.compile(
    r"\b(?P<partial>partial\s+)?"
    r"(?P<kind>callback\s+interface|interface\s+mixin|interface|dictionary|namespace|enum)"
    r"\s+(?P<name>\w+)"
    r"(?:\s*:\s*(?P<parent>\w+))?"
    r"\s*\{"
)

_MEMBER_KEYWORDS = ("iterable", "maplike", "setlike", "stringifier",
                    "async iterable", "constructor")


# Web IDL is the dialect Blink's own bindings generator reads, and it lives in
# exactly one place. The `.idl` extension is shared by two other languages in
# the tree, and this parser reads both of them wrongly rather than not at all:
#
#   chrome/common/extensions/api/*.idl   Chrome Extensions IDL. A `namespace`
#     wrapping `dictionary` and `interface Functions` blocks, so the whole
#     nested body came out as one member: 96 of the 1,081 facts it produced at
#     M151 had another declaration inside their own signature. The rest parsed
#     "successfully" and were reported as Web API changes -- `web_api_removed`
#     says "site-visible break", and no site can call chrome.fileManagerPrivate.
#
#   ui/accessibility/platform/ichromeaccessible.idl   MIDL, the COM interface
#     language, which happens to spell `interface X : IUnknown {` the same way.
#
# Reading a dialect this parser does not know produces confident wrong rows,
# which is worse than a stated gap. The extensions API is a real surface worth
# covering one day; it needs its own extractor and its own fact kind, not this
# one relabelled.
BLINK_IDL_DIR = "third_party/blink/renderer/"


def applies_to(path: str) -> bool:
    return path.endswith(".idl") and path.startswith(BLINK_IDL_DIR)


# ---------------------------------------------------------------------------
# Extended attributes
# ---------------------------------------------------------------------------


def parse_ext_attrs(text: str) -> Dict[str, object]:
    """``[RuntimeEnabled=Foo, Exposed=(Window,Worker), SecureContext]`` -> dict."""
    if not text:
        return {}
    out: Dict[str, object] = {}
    for part in split_top_level(text):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip()] = collapse_ws(value)
        else:
            out[part] = True
    return out


def _preceding_ext_attrs(masked: str, start: int) -> Tuple[Dict[str, object], int]:
    """Find an ``[...]`` block immediately before ``start`` (whitespace only)."""
    i = start - 1
    while i >= 0 and masked[i] in " \t\r\n":
        i -= 1
    if i < 0 or masked[i] != "]":
        return {}, start
    depth = 0
    j = i
    while j >= 0:
        if masked[j] == "]":
            depth += 1
        elif masked[j] == "[":
            depth -= 1
            if depth == 0:
                return parse_ext_attrs(masked[j + 1 : i]), j
        j -= 1
    return {}, start


def _match_brace(text: str, open_idx: int) -> Optional[int]:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def _member_name_and_type(body: str) -> Tuple[str, str]:
    """Classify one IDL member declaration and pull out its name."""
    text = collapse_ws(body)
    if not text:
        return "", ""

    if text.startswith("const "):
        m = re.search(r"\b(\w+)\s*=", text)
        return (m.group(1) if m else ""), "const"

    if re.match(r"^(readonly\s+)?(inherit\s+)?attribute\b", text):
        # Hyphens belong to the name. `\w` does not match one, so
        # `attribute CSSOMString margin-top` came out named `top` -- the same
        # name its neighbour `attribute CSSOMString top` already has, and
        # deduplication then kept one of the two. 138 member uids at M151
        # collided that way, most of them CSS descriptors, and a change to
        # either was invisible.
        m = re.search(r"([\w-]+)\s*$", text)
        return (m.group(1) if m else ""), "attribute"

    for keyword in ("async iterable", "iterable", "maplike", "setlike"):
        if text.startswith(keyword):
            return keyword, "declarative"

    if text.startswith("stringifier"):
        return "stringifier", "declarative"

    if text.startswith("constructor"):
        return "constructor", "operation"

    if "(" in text:
        head = text[: text.index("(")].strip()
        m = re.search(r"(\w+)$", head)
        if m:
            special = ""
            for token in ("getter", "setter", "deleter"):
                if re.search(rf"\b{token}\b", head):
                    special = token
            if m.group(1) in ("getter", "setter", "deleter"):
                # Anonymous special operation, e.g. "getter DOMString (unsigned long)".
                return f"{m.group(1)}()", "operation"
            name = m.group(1)
            if special:
                name = f"{special} {name}"
            return name, "operation"
        return "", "operation"

    # Dictionary field: "required DOMString name;" / "long count = 0;"
    m = re.search(r"(\w+)(?:\s*=\s*.+)?$", text)
    return (m.group(1) if m else ""), "field"


def _split_members(body: str) -> List[str]:
    """(offset, declaration) for each member, on top-level ';'.

    The offset travels with the text because a member's line number is made of
    it: without one, all 12,141 IDL members came out at line 0.
    """
    return [(o, p) for o, p in split_top_level_offsets(body, ";") if p]


def _enum_values(body: str) -> List[str]:
    return [v.strip().strip("\"'") for v in split_top_level(body, ",") if v.strip()]


# ---------------------------------------------------------------------------


def extract(text: str, rel_path: str) -> List[Fact]:
    masked = mask_comments(text)
    facts: List[Fact] = []
    pos = 0
    while True:
        m = _DEF_RE.search(masked, pos)
        if not m:
            break
        open_idx = masked.index("{", m.end() - 1)
        close_idx = _match_brace(masked, open_idx)
        if close_idx is None:
            break
        pos = close_idx + 1

        kind = collapse_ws(m.group("kind"))
        name = m.group("name")
        is_partial = bool(m.group("partial"))
        ext, _ = _preceding_ext_attrs(masked, m.start())
        body = masked[open_idx + 1 : close_idx]

        iface_attrs: Dict[str, object] = {
            "idl_kind": kind,
            "partial": is_partial,
            "inherits": m.group("parent") or "",
            "ext": ext,
        }
        if kind == "enum":
            iface_attrs["values"] = _enum_values(body)

        # Partial definitions are additive; the base definition owns identity.
        if not is_partial:
            facts.append(Fact(
                kind=KIND_IDL_INTERFACE,
                key=name,
                name=name,
                path=rel_path,
                line=line_of(masked, m.start()),
                attrs=iface_attrs,
            ))

        if kind == "enum":
            continue

        for member_offset, member_text in _split_members(body):
            # Member extended attributes lead the declaration:
            #   [RuntimeEnabled=Foo] readonly attribute double timestamp;
            decl = member_text.strip()
            member_ext: Dict[str, object] = {}
            if decl.startswith("["):
                close = _find_bracket_close(decl)
                if close is not None:
                    member_ext = parse_ext_attrs(decl[1:close])
                    decl = decl[close + 1 :].strip()
            member_name, member_type = _member_name_and_type(decl)
            if not member_name:
                continue
            facts.append(Fact(
                kind=KIND_IDL_MEMBER,
                key=f"{name}.{member_name}",
                name=member_name,
                path=rel_path,
                line=line_of(masked, open_idx + 1 + member_offset),
                attrs={
                    "interface": name,
                    "member_type": member_type,
                    "signature": collapse_ws(decl),
                    "ext": member_ext,
                    "runtime_enabled": member_ext.get("RuntimeEnabled", ""),
                    "from_partial": is_partial,
                },
            ))
    return facts


def _find_bracket_close(text: str) -> Optional[int]:
    depth = 0
    for i, c in enumerate(text):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i
    return None
