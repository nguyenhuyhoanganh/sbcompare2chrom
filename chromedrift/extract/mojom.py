"""Extract Mojo interfaces and method signatures.

Mojo is the ABI between Chromium's processes.  A downstream browser that
implements or calls a mojo interface -- which any vendor doing custom UI,
media or network work does -- breaks when a method signature moves.  Unlike an
IDL change this is not caught by web tests and often not by the compiler
either, because the mismatch shows up in generated bindings on the other side
of a process boundary.

Signature-level identity (name plus normalized parameter list) is therefore
what we key on: a reordered or retyped parameter must read as a change, not as
an unchanged method.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..model import KIND_MOJO_INTERFACE, KIND_MOJO_METHOD, Fact
from ._cpp import (collapse_ws, line_of, mask_comments, split_top_level,
                   split_top_level_offsets)

_MODULE_RE = re.compile(r"^\s*module\s+([\w.]+)\s*;", re.MULTILINE)
# The keyword is a named group because the line number comes from *its*
# position, not the match's. `\s*` after the newline crosses blank lines and
# comments -- which masking has turned into spaces -- so `m.start()` landed on
# the last content line before the interface: 1,453 of 1,455 interfaces at M151
# were reported at the wrong line, most of them pointing at the closing brace
# of the interface above.
_INTERFACE_RE = re.compile(
    r"(?:^|\n)\s*(?:\[[^\]]*\]\s*)?(?P<kw>interface)\s+(?P<name>\w+)\s*\{")
_ATTRS_RE = re.compile(r"\[([^\]]*)\]\s*$")


def applies_to(path: str) -> bool:
    return path.endswith(".mojom")


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


def _parse_method(decl: str) -> Optional[dict]:
    """Parse ``[Sync] Foo(int32 a, string b) => (bool ok);``."""
    text = collapse_ws(decl)
    if not text or "(" not in text:
        return None

    attrs = {}
    lead = re.match(r"^\[([^\]]*)\]\s*", text)
    if lead:
        attrs = {k.strip(): True for k in lead.group(1).split(",") if k.strip()}
        text = text[lead.end():]

    m = re.match(r"^(\w+)\s*\(", text)
    if not m:
        return None
    name = m.group(1)

    open_idx = text.index("(", m.start())
    close_idx = _match_paren(text, open_idx)
    if close_idx is None:
        return None
    params = text[open_idx + 1 : close_idx]

    response = ""
    rest = text[close_idx + 1 :].strip()
    if rest.startswith("=>"):
        rest = rest[2:].strip()
        if rest.startswith("("):
            rclose = _match_paren(rest, 0)
            if rclose is not None:
                response = rest[1:rclose]

    return {
        "name": name,
        "params": _normalize_params(params),
        "response": _normalize_params(response),
        "attrs": attrs,
    }


def _match_paren(text: str, open_idx: int) -> Optional[int]:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def _normalize_params(params: str) -> str:
    """Collapse a parameter list to a stable, comparable form."""
    parts = [collapse_ws(p) for p in split_top_level(params) if collapse_ws(p)]
    return ", ".join(parts)


def extract(text: str, rel_path: str) -> List[Fact]:
    masked = mask_comments(text)
    module_match = _MODULE_RE.search(masked)
    module = module_match.group(1) if module_match else ""

    facts: List[Fact] = []
    pos = 0
    while True:
        m = _INTERFACE_RE.search(masked, pos)
        if not m:
            break
        open_idx = masked.index("{", m.end() - 1)
        close_idx = _match_brace(masked, open_idx)
        if close_idx is None:
            break
        pos = close_idx + 1

        iface = m.group("name")
        qualified = f"{module}.{iface}" if module else iface
        body = masked[open_idx + 1 : close_idx]

        methods = []
        for offset, decl in split_top_level_offsets(body, ";"):
            parsed = _parse_method(decl)
            if not parsed:
                continue
            methods.append(parsed["name"])
            signature = f"{parsed['name']}({parsed['params']})"
            if parsed["response"]:
                signature += f" => ({parsed['response']})"
            facts.append(Fact(
                kind=KIND_MOJO_METHOD,
                key=f"{qualified}.{parsed['name']}",
                name=parsed["name"],
                path=rel_path,
                # The body starts one character past the brace, so the member's
                # offset inside it maps straight back onto the file.
                line=line_of(masked, open_idx + 1 + offset),
                attrs={
                    "interface": qualified,
                    "module": module,
                    "signature": signature,
                    "params": parsed["params"],
                    "response": parsed["response"],
                    "attrs": parsed["attrs"],
                },
            ))

        facts.append(Fact(
            kind=KIND_MOJO_INTERFACE,
            key=qualified,
            name=iface,
            path=rel_path,
            line=line_of(masked, m.start("kw")),
            attrs={"module": module, "method_count": len(methods),
                   "methods": sorted(methods)},
        ))
    return facts
