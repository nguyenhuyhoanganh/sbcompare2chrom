"""Minimal JSON5 / JSONC parser (stdlib only).

Chromium ships several machine-readable manifests in JSON5:
  - third_party/blink/renderer/platform/runtime_enabled_features.json5
  - chrome/browser/flag-metadata.json  (JSON with a leading license comment)

Python has no stdlib JSON5, and we deliberately avoid third-party deps so the
tool runs unmodified inside a locked-down corporate network.  This parser
covers the JSON5 subset Chromium actually uses:

  * // line comments and /* block */ comments
  * unquoted identifier keys
  * single-quoted strings
  * trailing commas in objects and arrays
  * hex / +leading-sign numbers, Infinity, NaN

It is intentionally lenient: unknown constructs raise Json5Error with a line
number so an extractor can skip one file rather than fail a whole snapshot.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["loads", "load", "Json5Error"]


class Json5Error(ValueError):
    """Raised when the input cannot be parsed."""


_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER_RE = re.compile(
    r"""
    [+-]?
    (?:
        0[xX][0-9a-fA-F]+          # hex
      | Infinity
      | NaN
      | (?:\d+\.?\d*|\.\d+)        # decimal
        (?:[eE][+-]?\d+)?          # exponent
    )
    """,
    re.VERBOSE,
)

_ESCAPES = {
    '"': '"',
    "'": "'",
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "0": "\0",
}


class _Parser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.n = len(text)

    # ---- helpers -------------------------------------------------------

    def _line(self) -> int:
        return self.s.count("\n", 0, self.i) + 1

    def _fail(self, msg: str) -> "Json5Error":
        near = self.s[self.i : self.i + 40].replace("\n", "\\n")
        return Json5Error(f"line {self._line()}: {msg} (near {near!r})")

    def skip_ws(self) -> None:
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n\f\v﻿":
                self.i += 1
            elif c == "/" and self.i + 1 < n:
                nxt = s[self.i + 1]
                if nxt == "/":
                    j = s.find("\n", self.i)
                    self.i = n if j == -1 else j + 1
                elif nxt == "*":
                    j = s.find("*/", self.i + 2)
                    if j == -1:
                        raise self._fail("unterminated block comment")
                    self.i = j + 2
                else:
                    return
            else:
                return

    def peek(self) -> str:
        return self.s[self.i] if self.i < self.n else ""

    # ---- grammar -------------------------------------------------------

    def parse(self) -> Any:
        self.skip_ws()
        value = self.parse_value()
        self.skip_ws()
        if self.i != self.n:
            raise self._fail("trailing content after top-level value")
        return value

    def parse_value(self) -> Any:
        self.skip_ws()
        c = self.peek()
        if c == "":
            raise self._fail("unexpected end of input")
        if c == "{":
            return self.parse_object()
        if c == "[":
            return self.parse_array()
        if c in "\"'":
            return self.parse_string()
        if self.s.startswith("true", self.i):
            self.i += 4
            return True
        if self.s.startswith("false", self.i):
            self.i += 5
            return False
        if self.s.startswith("null", self.i):
            self.i += 4
            return None
        m = _NUMBER_RE.match(self.s, self.i)
        if m:
            self.i = m.end()
            return _to_number(m.group(0))
        raise self._fail("unexpected token")

    def parse_object(self) -> dict:
        self.i += 1  # '{'
        out: dict = {}
        while True:
            self.skip_ws()
            c = self.peek()
            if c == "}":
                self.i += 1
                return out
            if c == "":
                raise self._fail("unterminated object")
            key = self.parse_key()
            self.skip_ws()
            if self.peek() != ":":
                raise self._fail("expected ':' after object key")
            self.i += 1
            out[key] = self.parse_value()
            self.skip_ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                continue
            if c == "}":
                self.i += 1
                return out
            raise self._fail("expected ',' or '}' in object")

    def parse_array(self) -> list:
        self.i += 1  # '['
        out: list = []
        while True:
            self.skip_ws()
            c = self.peek()
            if c == "]":
                self.i += 1
                return out
            if c == "":
                raise self._fail("unterminated array")
            out.append(self.parse_value())
            self.skip_ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                continue
            if c == "]":
                self.i += 1
                return out
            raise self._fail("expected ',' or ']' in array")

    def parse_key(self) -> str:
        c = self.peek()
        if c in "\"'":
            return self.parse_string()
        m = _IDENT_RE.match(self.s, self.i)
        if not m:
            raise self._fail("invalid object key")
        self.i = m.end()
        return m.group(0)

    def parse_string(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        buf = []
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c == quote:
                self.i += 1
                return "".join(buf)
            if c == "\\":
                self.i += 1
                if self.i >= n:
                    break
                e = s[self.i]
                if e == "u":
                    hexpart = s[self.i + 1 : self.i + 5]
                    if len(hexpart) < 4:
                        raise self._fail("truncated \\u escape")
                    buf.append(chr(int(hexpart, 16)))
                    self.i += 5
                elif e == "x":
                    hexpart = s[self.i + 1 : self.i + 3]
                    buf.append(chr(int(hexpart, 16)))
                    self.i += 3
                elif e == "\n":  # line continuation
                    self.i += 1
                else:
                    buf.append(_ESCAPES.get(e, e))
                    self.i += 1
                continue
            buf.append(c)
            self.i += 1
        raise self._fail("unterminated string")


def _to_number(tok: str) -> Any:
    sign = 1
    body = tok
    if body[0] in "+-":
        if body[0] == "-":
            sign = -1
        body = body[1:]
    if body == "Infinity":
        return sign * float("inf")
    if body == "NaN":
        return float("nan")
    if body[:2].lower() == "0x":
        return sign * int(body, 16)
    if "." in body or "e" in body.lower():
        return sign * float(body)
    return sign * int(body)


def loads(text: str) -> Any:
    """Parse a JSON5/JSONC string."""
    return _Parser(text).parse()


def load(path: str) -> Any:
    """Parse a JSON5/JSONC file from disk (UTF-8, BOM tolerated)."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        return loads(fh.read())
