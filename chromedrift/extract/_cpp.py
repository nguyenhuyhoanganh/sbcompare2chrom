"""Shared lexical helpers for scanning Chromium C++ declaration files.

We are not building a compiler.  The declarations we care about are macro
invocations and constant definitions written in a house style that has been
stable for years, so careful lexing beats a real parser: no toolchain, no
compile_commands.json, and it runs over a partial tree.

The one thing lexing must get right is *context*.  Chromium wraps default
feature states in preprocessor conditionals:

    BASE_FEATURE(kAudioServiceOutOfProcess,
    #if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
                 base::FEATURE_ENABLED_BY_DEFAULT
    #else
                 base::FEATURE_DISABLED_BY_DEFAULT
    #endif
    );

For a browser that ships on Android only, reading that as "enabled" is not a
rounding error -- it inverts the conclusion.  `resolve_platform_state` walks
the conditional chain and answers per platform.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Platform BUILDFLAGs that matter when deciding "does this apply to us".
PLATFORM_FLAGS = {
    "android": {"IS_ANDROID", "IS_ANDROID_DESKTOP"},
    "windows": {"IS_WIN"},
    "mac": {"IS_MAC", "IS_APPLE"},
    "linux": {"IS_LINUX"},
    "chromeos": {"IS_CHROMEOS", "IS_CHROMEOS_ASH", "IS_CHROMEOS_LACROS"},
    "ios": {"IS_IOS", "IS_APPLE"},
}

ALL_PLATFORM_MACROS = set().union(*PLATFORM_FLAGS.values())


def mask_comments(text: str) -> str:
    """Blank out comments while preserving length, offsets and line numbers.

    Returning a same-length string means byte offsets computed on the masked
    text still map onto the original, so reported line numbers stay accurate.
    String literals are preserved because feature names live inside them.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                while i < n and text[i] != "\n":
                    out[i] = " "
                    i += 1
                continue
            if nxt == "*":
                end = text.find("*/", i + 2)
                end = n if end == -1 else end + 2
                for j in range(i, end):
                    if out[j] != "\n":
                        out[j] = " "
                i = end
                continue
        i += 1
    return "".join(out)


def balanced_args(text: str, open_paren: int) -> Tuple[str, int]:
    """Return (inner_text, index_after_close) for the paren at ``open_paren``.

    Skips parens inside string and char literals.  Raises ValueError if the
    parenthesis is never closed (truncated file / bad fetch).
    """
    if text[open_paren] != "(":
        raise ValueError("balanced_args must start on '('")
    depth = 0
    i, n = open_paren, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    break
                i += 1
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : i], i + 1
        i += 1
    raise ValueError("unbalanced parentheses")


def split_top_level(text: str, sep: str = ",") -> List[str]:
    """Split on ``sep`` ignoring separators nested in (), [], {}, <> or strings.

    ``<>`` counting is deliberately conservative: it only nests when the '<'
    is preceded by an identifier character, so comparison operators inside a
    default value do not corrupt the split.
    """
    parts, buf = [], []
    depth = 0
    angle = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            quote = c
            buf.append(c)
            i += 1
            while i < n:
                buf.append(text[i])
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "<" and i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
            angle += 1
        elif c == ">" and angle > 0:
            angle -= 1
        elif c == sep and depth == 0 and angle == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Preprocessor conditional evaluation
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\s*(\|\||&&|!|\(|\)|[A-Za-z_][A-Za-z0-9_]*|\d+|.)")


def _tokenize(expr: str) -> List[str]:
    tokens, pos = [], 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            break
        tok = m.group(1)
        pos = m.end()
        if tok.strip():
            tokens.append(tok)
    return tokens


class _CondEval:
    """Three-valued evaluator: True / False / None (unknown).

    Unknown propagates, so a condition we cannot decide yields None and the
    caller degrades to 'conditional' rather than inventing an answer.
    """

    def __init__(self, tokens: List[str], platform: str):
        self.t = tokens
        self.i = 0
        self.platform = platform
        self.flags = PLATFORM_FLAGS.get(platform, set())

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self) -> Optional[str]:
        tok = self.peek()
        if tok is not None:
            self.i += 1
        return tok

    def parse_or(self) -> Optional[bool]:
        left = self.parse_and()
        while self.peek() == "||":
            self.next()
            right = self.parse_and()
            if left is True or right is True:
                left = True
            elif left is False and right is False:
                left = False
            else:
                left = None
        return left

    def parse_and(self) -> Optional[bool]:
        left = self.parse_unary()
        while self.peek() == "&&":
            self.next()
            right = self.parse_unary()
            if left is False or right is False:
                left = False
            elif left is True and right is True:
                left = True
            else:
                left = None
        return left

    def parse_unary(self) -> Optional[bool]:
        tok = self.peek()
        if tok == "!":
            self.next()
            val = self.parse_unary()
            return None if val is None else (not val)
        return self.parse_atom()

    def parse_atom(self) -> Optional[bool]:
        tok = self.next()
        if tok is None:
            return None
        if tok == "(":
            val = self.parse_or()
            if self.peek() == ")":
                self.next()
            return val
        if tok in ("BUILDFLAG", "defined"):
            if self.peek() == "(":
                self.next()
                inner = self.next()
                depth = 1
                while self.peek() is not None and depth:
                    p = self.peek()
                    if p == "(":
                        depth += 1
                    elif p == ")":
                        depth -= 1
                        if depth == 0:
                            self.next()
                            break
                    self.next()
                return self._flag_value(inner)
            return None
        if tok in ("0", "false"):
            return False
        if tok in ("1", "true"):
            return True
        return None  # unknown identifier

    def _flag_value(self, flag: Optional[str]) -> Optional[bool]:
        if not flag:
            return None
        if flag in self.flags:
            return True
        if flag in ALL_PLATFORM_MACROS:
            return False  # a different platform's flag
        return None  # non-platform buildflag: undecidable here


def eval_condition(expr: str, platform: str) -> Optional[bool]:
    """Evaluate a preprocessor condition for one platform. None = unknown."""
    return _CondEval(_tokenize(expr), platform).parse_or()


_MACRO_RE = re.compile(r"\b(?:BUILDFLAG|defined)\s*\(\s*(\w+)\s*\)|\b([A-Z][A-Z0-9_]{2,})\b")


def conditional_spans(text: str) -> List[Tuple[int, int, str]]:
    """``(start, end, expression)`` for every ``#if`` block in a file.

    The guard that matters usually wraps the whole declaration rather than
    sitting inside it, so a caller needs to ask "what conditions enclose this
    offset", not "what conditions appear in this snippet".
    """
    spans: List[Tuple[int, int, str]] = []
    stack: List[Tuple[int, str]] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        m = _DIRECTIVE_RE.match(raw_line)
        if m:
            directive, rest = m.group(1), m.group(2).strip()
            if directive in ("if", "ifdef", "ifndef"):
                expr = rest
                if directive == "ifdef":
                    expr = f"defined({rest})"
                elif directive == "ifndef":
                    expr = f"!defined({rest})"
                stack.append((offset + len(raw_line), expr))
            elif directive in ("elif", "else"):
                if stack:
                    start, expr = stack.pop()
                    spans.append((start, offset, expr))
                    new_expr = rest if directive == "elif" else f"!({expr})"
                    stack.append((offset + len(raw_line), new_expr))
            elif directive == "endif":
                if stack:
                    start, expr = stack.pop()
                    spans.append((start, offset, expr))
        offset += len(raw_line)
    while stack:  # unterminated #if: treat as running to end of file
        start, expr = stack.pop()
        spans.append((start, len(text), expr))
    return spans


def enclosing_conditions(spans: List[Tuple[int, int, str]], index: int) -> List[str]:
    return [expr for start, end, expr in spans if start <= index < end]


def condition_macros(block: str) -> List[str]:
    """Every preprocessor macro named in the ``#if`` directives of a block.

    A vendor fork does not usually replace upstream code; it adds its own
    beside it and picks between them at build time::

        #if defined(SBROWSER_CUSTOM_DOWNLOADS)
          ... Samsung's implementation ...
        #else
          ... Chromium's ...
        #endif

    Both versions ship. Comparing values alone reports such a declaration as
    identical to upstream, because upstream's branch really is untouched --
    while the branch that actually runs is the vendor's. Recording the macro
    names makes that visible, and lets a profile say which of them are ours.
    """
    macros: List[str] = []
    for raw_line in block.splitlines():
        m = _DIRECTIVE_RE.match(raw_line)
        if not m or m.group(1) in ("else", "endif"):
            continue
        for a, b in _MACRO_RE.findall(m.group(2)):
            name = a or b
            if name and name not in macros:
                macros.append(name)
    return macros


_DIRECTIVE_RE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")


def conditional_values(block: str, value_re: re.Pattern) -> List[Tuple[List[Tuple[str, bool]], str]]:
    """Find every ``value_re`` match in ``block`` with its conditional context.

    Returns a list of ``(context, value)`` where context is a list of
    ``(condition_expression, is_taken_branch)`` pairs describing the #if chain
    guarding that value.  ``#else`` branches appear as the negation of every
    preceding condition in the same chain.
    """
    results: List[Tuple[List[Tuple[str, bool]], str]] = []
    stack: List[List[Tuple[str, bool]]] = []  # each level: list of (expr, taken)

    for raw_line in block.splitlines():
        m = _DIRECTIVE_RE.match(raw_line)
        if m:
            directive, rest = m.group(1), m.group(2).strip()
            if directive in ("if", "ifdef", "ifndef"):
                expr = rest
                if directive == "ifdef":
                    expr = f"defined({rest})"
                elif directive == "ifndef":
                    expr = f"!defined({rest})"
                stack.append([(expr, True)])
            elif directive == "elif":
                if stack:
                    prev = [(e, False) for e, _ in stack[-1]]
                    stack[-1] = prev + [(rest, True)]
            elif directive == "else":
                if stack:
                    stack[-1] = [(e, False) for e, _ in stack[-1]]
            elif directive == "endif":
                if stack:
                    stack.pop()
            continue
        for vm in value_re.finditer(raw_line):
            context: List[Tuple[str, bool]] = []
            for level in stack:
                context.extend(level)
            results.append((context, vm.group(0)))
    return results


def resolve_platform_state(block: str, value_re: re.Pattern,
                           platforms: Optional[List[str]] = None) -> Dict[str, str]:
    """Map platform -> the value that applies there.

    ``"conditional"`` means the guard depends on something this lexer cannot
    decide (a non-platform buildflag, a feature-specific define).  That is an
    honest answer and reports surface it as such rather than guessing.
    """
    platforms = platforms or list(PLATFORM_FLAGS)
    found = conditional_values(block, value_re)
    if not found:
        return {}
    if len(found) == 1 and not found[0][0]:
        return {p: found[0][1] for p in platforms}

    out: Dict[str, str] = {}
    for platform in platforms:
        chosen: Optional[str] = None
        unknown = False
        for context, value in found:
            verdict: Optional[bool] = True
            for expr, want_true in context:
                val = eval_condition(expr, platform)
                if val is None:
                    verdict = None
                    break
                actual = val if want_true else (not val)
                if not actual:
                    verdict = False
                    break
            if verdict is True:
                chosen = value
                break
            if verdict is None:
                unknown = True
        if chosen is not None:
            out[platform] = chosen
        elif unknown:
            out[platform] = "conditional"
        else:
            out[platform] = "not_compiled"
    return out
