"""Extract the Mojo ABI: the calls that cross a process boundary and the data
that travels along them.

Mojo is the ABI between Chromium's processes.  Anything that implements or
calls a mojo interface -- which anything doing custom UI, media or network work
does -- breaks when a method signature moves.  Unlike an IDL change this is not
caught by web tests and often not by the compiler either, because the mismatch
shows up in generated bindings on the other side of a process boundary.

Signature-level identity (name plus normalized parameter list) is therefore
what we key on: a reordered or retyped parameter must read as a change, not as
an unchanged method.

Both halves are read, and for a while only one was.  `interface` alone is 1,581
of the 5,911 declarations in the M151 tree -- 26% -- and a struct field
changing type breaks deserialization on the far side exactly the way a moved
parameter does, with the compiler just as silent.  Structs, unions and their
fields become facts of their own; an enum becomes one fact carrying its member
list, because members alone are 17,061 declarations and adding one is Mojo's
ordinary way of extending a type, so a fact each would bury the report to say
what a `values` delta says in one row.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..model import (KIND_MOJO_ENUM, KIND_MOJO_FIELD, KIND_MOJO_INTERFACE,
                     KIND_MOJO_METHOD, KIND_MOJO_STRUCT, Fact)
from ._cpp import (PLATFORM, collapse_ws, line_of, mask_comments,
                   mojom_platform_state, split_top_level,
                   split_top_level_offsets)

_MODULE_RE = re.compile(r"^\s*module\s+([\w.]+)\s*;", re.MULTILINE)
_MIN_VERSION_RE = re.compile(r"\bMinVersion\s*=\s*(\d+)")
# The keyword is a named group because the line number comes from *its*
# position, not the match's. `\s*` after the newline crosses blank lines and
# comments -- which masking has turned into spaces -- so `m.start()` landed on
# the last content line before the interface: 1,453 of 1,455 interfaces at M151
# were reported at the wrong line, most of them pointing at the closing brace
# of the interface above.
_INTERFACE_RE = re.compile(
    r"(?:^|\n)\s*(?:\[(?P<attrs>[^\]]*)\]\s*)?(?P<kw>interface)"
    r"\s+(?P<name>\w+)\s*\{")

# The data half of the ABI: what travels along the calls the interfaces declare.
# Only `interface` was read before, which is 1,581 of the 5,911 declarations in
# the M151 tree -- 26%. A struct field changing type breaks deserialization on
# the far side of the process boundary exactly the way a moved method parameter
# does, and neither breaks the build.
_DATA_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:\[(?P<attrs>[^\]]*)\]\s*)?"
    r"(?P<kw>struct|union|enum)\s+(?P<name>\w+)\s*\{")


def _is_stable(attr_text: Optional[str]) -> bool:
    """`[Stable]` — the declaration Mojo promises stays wire-compatible.

    Ordinals are assigned by lexical position unless written, so moving a
    member changes the wire id of everything after it. Chromium does that
    freely and it costs nothing, because both ends of an unstable interface
    are always rebuilt together: measured M148 -> M151, 1,110 members shifted
    position across the tree. Inside `[Stable]`, the mojom documentation says
    existing ordinals must not move, and Chromium honours it -- 0 of those
    1,110 are in a stable declaration.

    So position is recorded here and nowhere else. Reporting all 1,110 would
    report file layout as an ABI event; reporting none leaves the one case
    where it is an ABI event invisible.
    """
    if not attr_text:
        return False
    return any(part.strip() == "Stable"
               for part in split_top_level(attr_text))


def _conditions(attr_text: Optional[str]) -> List[str]:
    """The build conditions in an attribute block, ignoring everything else.

    `[EnableIf=is_win]` and `[EnableIfNot=is_android|is_ios]` are the only two
    that decide whether a declaration is in the binary. `[Sync]`,
    `[MinVersion=3]` and the rest say something about how it behaves, which is
    a different question and is compared rather than resolved.
    """
    if not attr_text:
        return []
    return [part for part in
            (p.strip() for p in split_top_level(attr_text))
            if part.startswith("EnableIf")]


def _platform_attrs(conditions: List[str], inherited: int = 0) -> dict:
    """`conditions` and `platform_state`, or nothing when unconditional.

    Written in the shape `base_features` and `prefs` already use, because
    `score._not_in_build` reads one key on every kind and a second spelling
    here would mean it silently kept skipping Mojo.
    """
    if not conditions:
        return {}
    state = mojom_platform_state(conditions)
    if state is None:
        return {}
    out = {"conditions": conditions, "platform_state": {PLATFORM: state}}
    if inherited:
        # Which of them are the container's rather than this declaration's.
        # A field losing its own `[EnableIf]` and a struct losing the one
        # around it resolve to the same verdict and are not the same edit,
        # and the verdict alone could not tell them apart.
        out["inherited_conditions"] = conditions[:inherited]
    return out

# `[MinVersion=1] url.mojom.Url filesystem_url@0;` and `int32 count = 5;`.
#
# The leading attribute block and the trailing default are peeled off before
# this runs, rather than being groups of their own. Both contain an `=`, and a
# greedy type is what makes the rest work -- `array<uint8>? data` has to keep
# its whole type, and the name is the last identifier. Left in one pattern, the
# greedy type ate the `=` and `int32 retries = 5` came out as a field named
# `5` of type `int32 retries =`.
_FIELD_RE = re.compile(r"^(?P<type>.+)\s+(?P<name>\w+)(?:@(?P<ordinal>\d+))?$")
_FIELD_ATTRS_RE = re.compile(r"^\[([^\]]*)\]\s*")

# `kFoo = 1` / `kBar`. The value is compared as declared, because an enum's
# numbers are the wire format.
_ENUM_VALUE_RE = re.compile(r"^(?P<name>\w+)(?:\s*=\s*(?P<value>.+))?$")


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

    # `Foo@0(...)` is a method pinned to an explicit ordinal, which is how a
    # versioned interface keeps its wire order while methods move in the file.
    # The ordinal is part of the ABI and the name is not the same thing, so it
    # is captured rather than skipped -- and before it was neither: the regex
    # required `(` straight after the name, so 269 declarations across 23 files
    # at M151 produced no fact at all, silently, on the surface this tool
    # ranks highest.
    m = re.match(r"^(\w+)\s*(?:@(\d+))?\s*\(", text)
    if not m:
        return None
    name = m.group(1)
    ordinal = m.group(2)

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

    out = {
        "name": name,
        "params": _normalize_params(params),
        "response": _normalize_params(response),
        "attrs": attrs,
    }
    if ordinal is not None:
        out["ordinal"] = ordinal
    return out


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
        iface_conditions = _conditions(m.group("attrs"))
        iface_stable = _is_stable(m.group("attrs"))

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
                    # Recorded only when present, so a method that never had
                    # one compares equal to how it always was.
                    **({"ordinal": parsed["ordinal"]}
                       if "ordinal" in parsed else {}),
                    **_platform_attrs(
                        iface_conditions
                        + _conditions(",".join(parsed["attrs"])),
                        inherited=len(iface_conditions)),
                    **({"position": len(methods) - 1, "stable": True}
                       if iface_stable else {}),
                },
            ))

        facts.append(Fact(
            kind=KIND_MOJO_INTERFACE,
            key=qualified,
            name=iface,
            path=rel_path,
            line=line_of(masked, m.start("kw")),
            attrs={"module": module, "method_count": len(methods),
                   "methods": sorted(methods),
                   **({"stable": True} if iface_stable else {}),
                   **_platform_attrs(iface_conditions)},
        ))

    facts.extend(extract_data_types(masked, rel_path, module))
    return facts


# ---------------------------------------------------------------------------
# Structs, unions and enums: the data that travels across the boundary
# ---------------------------------------------------------------------------


def _spans(masked: str) -> List[dict]:
    """Every declaration in the file, with the range it occupies.

    Collected in one pass over all four keywords rather than per kind, because
    the qualified name of a nested declaration needs the ones enclosing it.
    Nesting is normal: 357 enums at M151 are declared inside the struct or
    interface that uses them, and Mojo names those `Outer.Inner`.
    """
    out: List[dict] = []
    for pattern in (_INTERFACE_RE, _DATA_RE):
        for m in pattern.finditer(masked):
            try:
                open_idx = masked.index("{", m.end() - 1)
            except ValueError:  # pragma: no cover - truncated file
                continue
            close_idx = _match_brace(masked, open_idx)
            if close_idx is None:
                continue
            out.append({"kw": m.group("kw"), "name": m.group("name"),
                        "decl": m.start("kw"), "open": open_idx,
                        "close": close_idx,
                        "stable": _is_stable(m.group("attrs")),
                        "conditions": _conditions(m.group("attrs"))})
    out.sort(key=lambda s: s["open"])
    return out


def _qualified(span: dict, spans: List[dict], module: str) -> str:
    """`module.Outer.Inner` -- the name Mojo itself uses for a nested type."""
    chain = [s["name"] for s in spans
             if s["open"] < span["decl"] and span["close"] < s["close"]]
    chain.append(span["name"])
    return ".".join(([module] if module else []) + chain)


def _enclosing_conditions(span: dict, spans: List[dict]) -> List[str]:
    """This declaration's build conditions plus every enclosing one.

    The same chain `_qualified` walks, for the same reason: an enum declared
    inside a struct marked `[EnableIf=is_android]` is not in our binary either,
    and reading only its own attributes would say it is.
    """
    out: List[str] = []
    for s in spans:
        if s["open"] < span["decl"] and span["close"] < s["close"]:
            out.extend(s["conditions"])
    out.extend(span["conditions"])
    return out


def _own_body(span: dict, spans: List[dict], masked: str) -> str:
    """The body with nested declarations blanked out, offsets preserved.

    Blanked rather than removed so an offset into the result still maps onto
    the file and the line numbers stay right -- the same reason
    `webui_controls.template_body` blanks its leading TypeScript. Without this
    a nested enum's members would also be counted as fields of the struct
    around it.
    """
    start, end = span["open"] + 1, span["close"]
    body = list(masked[start:end])
    for other in spans:
        if other is span or not (start <= other["decl"] and other["close"] < end):
            continue
        for i in range(other["decl"] - start, min(other["close"] + 1 - start, len(body))):
            if body[i] != "\n":
                body[i] = " "
    return "".join(body)


def _field_facts(span, spans, masked, module, rel_path, qualified):
    """One fact per struct or union field, keyed by the type that owns it."""
    facts: List[Fact] = []
    names: List[str] = []
    body = _own_body(span, spans, masked)
    base = span["open"] + 1
    outer = _enclosing_conditions(span, spans)
    for offset, decl in split_top_level_offsets(body, ";"):
        text = collapse_ws(decl)
        if not text:
            continue
        lead = _FIELD_ATTRS_RE.match(text)
        field_attrs = lead.group(1).strip() if lead else ""
        if lead:
            text = text[lead.end():]
        default = ""
        eq = text.find("=")
        if eq != -1:
            default = text[eq + 1:].strip()
            text = text[:eq].strip()
        m = _FIELD_RE.match(text)
        if not m:
            continue
        name = m.group("name")
        names.append(name)
        attrs = {
            "struct": qualified,
            "module": module,
            "type": collapse_ws(m.group("type")),
        }
        # Recorded only when present, so an ordinary field and one that simply
        # never had an ordinal compare as the same thing.
        if m.group("ordinal"):
            attrs["ordinal"] = m.group("ordinal")
        if default:
            attrs["default"] = collapse_ws(default)
        if field_attrs:
            attrs["attrs"] = collapse_ws(field_attrs)
            version = _MIN_VERSION_RE.search(field_attrs)
            if version:
                # Its own key rather than a substring of `attrs`, so a tier
                # can be read without parsing prose: `[MinVersion=N]` is how
                # mojom says an older peer may not send this at all.
                attrs["min_version"] = version.group(1)
        attrs.update(_platform_attrs(outer + _conditions(field_attrs),
                                     inherited=len(outer)))
        if span.get("stable"):
            attrs["stable"] = True
            # Only here: see `_is_stable`. Outside a stable declaration this
            # number moves whenever Chromium tidies a file and means nothing.
            attrs["position"] = len(names) - 1
        facts.append(Fact(
            kind=KIND_MOJO_FIELD,
            key=f"{qualified}.{name}",
            name=name,
            path=rel_path,
            line=line_of(masked, base + offset),
            attrs=attrs,
        ))
    return facts, names


def _enum_values(span, spans, masked) -> List[str]:
    """`kFoo = 1` for every member, in declaration order.

    Carried as one list on the enum rather than as a fact per member. Members
    are 17,061 of the tree's declarations at M151 -- more than every other new
    fact combined -- and adding one is Mojo's ordinary way of extending a type,
    so a fact each would bury the report to report the same thing a `values`
    delta already says in one row. This is the shape `web_idl` already uses for
    an IDL enum.
    """
    values: List[str] = []
    for _, decl in split_top_level_offsets(_own_body(span, spans, masked), ","):
        text = collapse_ws(decl)
        if not text:
            continue
        m = _ENUM_VALUE_RE.match(text)
        if not m:
            continue
        values.append(f"{m.group('name')} = {collapse_ws(m.group('value'))}"
                      if m.group("value") else m.group("name"))
    return values


def extract_data_types(masked: str, rel_path: str, module: str) -> List[Fact]:
    """Structs, unions and enums, including the ones nested inside others."""
    spans = _spans(masked)
    facts: List[Fact] = []
    for span in spans:
        if span["kw"] == "interface":
            continue
        qualified = _qualified(span, spans, module)
        line = line_of(masked, span["decl"])
        if span["kw"] == "enum":
            facts.append(Fact(
                kind=KIND_MOJO_ENUM, key=qualified, name=span["name"],
                path=rel_path, line=line,
                attrs={"module": module,
                       "values": _enum_values(span, spans, masked),
                       **({"stable": True} if span.get("stable") else {}),
                       **_platform_attrs(_enclosing_conditions(span, spans))},
            ))
            continue
        fields, names = _field_facts(span, spans, masked, module, rel_path,
                                     qualified)
        facts.extend(fields)
        facts.append(Fact(
            kind=KIND_MOJO_STRUCT, key=qualified, name=span["name"],
            path=rel_path, line=line,
            # `fields` is not compared, for the reason `mojo_interface.methods`
            # is not: every field is already a fact of its own, so comparing the
            # list would report one ABI change twice, once vaguely and once
            # precisely. `mojo_kind` is compared -- a struct becoming a union is
            # a different wire format under the same name.
            attrs={"module": module, "mojo_kind": span["kw"],
                   "field_count": len(names), "fields": sorted(names),
                   **({"stable": True} if span.get("stable") else {}),
                   **_platform_attrs(_enclosing_conditions(span, spans))},
        ))
    return facts
