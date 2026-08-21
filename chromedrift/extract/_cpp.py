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

Reading the global value instead of the Windows branch is not a rounding
error -- it inverts the conclusion.  `resolve_platform_state` walks the
conditional chain and answers for the desktop platform this product ships.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# This tool targets one product: a Chromium-based desktop browser on Windows.
# The platform is fixed rather than configurable, because getting it wrong does
# not degrade the answer, it inverts it: AudioServiceOutOfProcess reads
# "enabled" globally and resolves differently per platform, and 14 of 187
# features in a single file diverge that way. A setting nobody checks is a way
# to be silently wrong, so there is no setting.
PLATFORM = "windows"

PLATFORM_FLAGS = {PLATFORM: {"IS_WIN"}}

# Every other platform's macros still have to be recognised, so a guard naming
# one of them evaluates to False for us instead of "undecidable".
OTHER_PLATFORM_MACROS = {
    "IS_ANDROID", "IS_ANDROID_DESKTOP",
    "IS_MAC", "IS_APPLE",
    "IS_LINUX",
    "IS_CHROMEOS", "IS_CHROMEOS_ASH", "IS_CHROMEOS_LACROS",
    "IS_IOS", "IS_FUCHSIA",
}

ALL_PLATFORM_MACROS = set().union(*PLATFORM_FLAGS.values()) | OTHER_PLATFORM_MACROS


# GRIT, the resource pipeline behind every WebUI template, spells its build
# conditions in Python rather than C++: `<if expr="not is_win">`. The operators
# and platform names differ but the question is identical -- does this ship on
# Windows -- so it is answered by the same three-valued evaluator rather than a
# second one that could disagree with it.
_GRIT_PLATFORM = {
    "is_win": "IS_WIN", "is_macosx": "IS_MAC", "is_linux": "IS_LINUX",
    "is_chromeos": "IS_CHROMEOS", "is_android": "IS_ANDROID", "is_ios": "IS_IOS",
    # Windows is not POSIX, and nothing else in this table implies it.
    "is_posix": "IS_LINUX",
}
_GRIT_WORD_RE = re.compile(r"\b(not|and|or|[A-Za-z_]\w*)\b")


def eval_grit_condition(expr: str, platform: str = PLATFORM) -> Optional[bool]:
    """Evaluate a GRIT `<if expr>` for our platform. None = undecidable.

    Anything that is not a platform name -- `_google_chrome` and other branding
    or build switches -- stays undecidable, exactly as a non-platform BUILDFLAG
    does in C++. Guessing there would be the same mistake in a new place.
    """
    def rewrite(m: "re.Match") -> str:
        word = m.group(1)
        if word == "not":
            return "!"
        if word == "and":
            return "&&"
        if word == "or":
            return "||"
        if word in _GRIT_PLATFORM:
            return f"BUILDFLAG({_GRIT_PLATFORM[word]})"
        return word
    return eval_condition(_GRIT_WORD_RE.sub(rewrite, expr), platform)


# Mojom spells the same condition as an attribute on the declaration:
# `[EnableIf=is_win]`, `[EnableIfNot=is_android|is_ios]`. Third dialect, one
# question, so it resolves through the same evaluator rather than growing a
# fourth answer that could disagree with the other three.
#
# The names are GN build-flag names. They overlap GRIT's without matching them
# -- mojom says `is_mac` where GRIT says `is_macosx` -- so this is its own
# table rather than a reuse of the one above.
_MOJOM_PLATFORM = {
    "is_win": "IS_WIN",
    "is_android": "IS_ANDROID",
    "is_mac": "IS_MAC",
    "is_apple": "IS_APPLE",
    "is_ios": "IS_IOS",
    "is_ios_iphoneos": "IS_IOS",
    "is_linux": "IS_LINUX",
    "is_chromeos": "IS_CHROMEOS",
    "is_fuchsia": "IS_FUCHSIA",
    # Windows is not POSIX, under either spelling. Same call the GRIT table
    # makes above, for the same reason.
    "is_posix": "IS_LINUX",
    "is_non_android_posix": "IS_LINUX",
}
_MOJOM_ENABLE_RE = re.compile(r"^EnableIf(Not)?=(.+)$")


def eval_mojom_condition(expr: str, platform: str = PLATFORM) -> Optional[bool]:
    """Evaluate one mojom `[EnableIf=...]` attribute. None = undecidable.

    `|` is the only operator the attribute allows, and it means or. Rewriting
    into the C++ dialect rather than evaluating here is what makes the unknown
    cases come out right for free: `is_win|enable_pdf` is true on Windows
    whatever `enable_pdf` turns out to be, and the three-valued `||` already
    knows that.

    Anything that is not a platform name stays undecidable -- 40 of the 68
    distinct attributes in the M151 tree are build flags like
    `enable_print_preview` and `webnn_enable_graph_dump`. Guessing there would
    be the same mistake in a new place.
    """
    m = _MOJOM_ENABLE_RE.match(expr.strip())
    if not m:
        return None
    names = [n.strip() for n in m.group(2).split("|")]
    rewritten = " || ".join(
        f"BUILDFLAG({_MOJOM_PLATFORM[n]})" if n in _MOJOM_PLATFORM else n
        for n in names)
    if m.group(1):  # EnableIfNot
        rewritten = f"!({rewritten})"
    return eval_condition(rewritten, platform)


def guard_platform_state(conditions: List[str], evaluate,
                         platform: str = PLATFORM) -> Optional[str]:
    """"not_compiled" / "compiled" / "conditional" for a set of guards.

    One definition, two dialects: `#if BUILDFLAG(IS_CHROMEOS)` in C++ and
    `<if expr="is_chromeos">` in a GRIT template ask the same question, and the
    answer decides the same thing -- whether the declaration is in the binary we
    ship. Guards are ANDed: any one of them false takes it out.
    """
    if not conditions:
        return None
    verdict: Optional[bool] = True
    for expr in conditions:
        value = evaluate(expr, platform)
        if value is False:
            return "not_compiled"
        if value is None:
            verdict = None
    return "compiled" if verdict is True else "conditional"


def cpp_platform_state(conditions: List[str],
                       platform: str = PLATFORM) -> Optional[str]:
    """Whether a C++ `#if` chain puts this declaration in our binary."""
    return guard_platform_state(conditions, eval_condition, platform)


def grit_platform_state(conditions: List[str],
                        platform: str = PLATFORM) -> Optional[str]:
    """"not_compiled" / "compiled" / "conditional" for a set of GRIT guards.

    A control behind `<if expr="is_chromeos">` is not in our binary, so a change
    to it is not a change to our product. Nothing scored those down before,
    because the penalty reads `platform_state` and only C++ declarations
    carried one.
    """
    return guard_platform_state(conditions, eval_grit_condition, platform)


def mojom_platform_state(conditions: List[str],
                         platform: str = PLATFORM) -> Optional[str]:
    """Whether a mojom `[EnableIf]` chain puts this declaration in our binary.

    Nothing read these before. `platform_state` existed on four of the sixteen
    fact kinds -- 2,264 of 29,118 facts -- and none of them were Mojo, so the
    scoring stage could not zero an Android-only declaration and a field that
    only exists on Android scored 80 at the top of a Windows report. Measured
    at M151: 256 declarations are `EnableIf=is_android` and 186 `is_win`.
    """
    return guard_platform_state(conditions, eval_mojom_condition, platform)


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
    return [part for _, part in split_top_level_offsets(text, sep)]


def split_top_level_offsets(text: str, sep: str = ",") -> List[Tuple[int, str]]:
    """``split_top_level`` with each part's offset into ``text``.

    The offset is what a line number is made of, and four of the thirteen fact
    kinds had none because the splitter threw it away: every Mojo method and
    every IDL member came out at line 0. Both callers of the plain form go
    through this one, so the scanner has a single definition.
    """
    parts: List[Tuple[int, str]] = []
    buf: List[str] = []
    start = 0
    depth = 0
    angle = 0
    i, n = 0, len(text)

    def flush(end: int) -> None:
        raw = "".join(buf)
        lead = len(raw) - len(raw.lstrip())
        parts.append((start + lead, raw.strip()))

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
            flush(i)
            buf = []
            i += 1
            start = i
            continue
        buf.append(c)
        i += 1
    flush(n)
    return parts


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


def eval_condition(expr: str, platform: str = PLATFORM) -> Optional[bool]:
    """Evaluate a preprocessor condition for Windows. None = unknown."""
    return _CondEval(_tokenize(expr), platform).parse_or()


_MACRO_RE = re.compile(r"\b(?:BUILDFLAG|defined)\s*\(\s*(\w+)\s*\)|\b([A-Z][A-Z0-9_]{2,})\b")


_IFNDEF_RE = re.compile(r"^\s*#\s*ifndef\s+(\w+)\s*$")
_DEFINE_RE = re.compile(r"^\s*#\s*define\s+(\w+)\b")


def _include_guard_lines(lines: List[str]) -> set:
    """Line numbers of `#ifndef X` that open an include guard, not a condition.

    The idiom is exact and unambiguous -- `#ifndef X` immediately followed by
    `#define X` -- so recognising it needs no filename heuristic and no guess
    about where the block ends.
    """
    out = set()
    for i, line in enumerate(lines):
        m = _IFNDEF_RE.match(line)
        if not m:
            continue
        for follower in lines[i + 1:i + 4]:
            if not follower.strip():
                continue
            d = _DEFINE_RE.match(follower)
            if d and d.group(1) == m.group(1):
                out.add(i)
            break
    return out


def conditional_spans(text: str) -> List[Tuple[int, int, str]]:
    """``(start, end, expression)`` for every ``#if`` block in a file.

    The guard that matters usually wraps the whole declaration rather than
    sitting inside it, so a caller needs to ask "what conditions enclose this
    offset", not "what conditions appear in this snippet".
    """
    spans: List[Tuple[int, int, str]] = []
    # Per open level: [start offset, conditions holding in this branch,
    #                  every branch expression seen at this level so far]
    stack: List[list] = []
    offset = 0
    lines = text.splitlines(keepends=True)
    guard_lines = _include_guard_lines(lines)

    def close(level: list, end: int) -> None:
        start, holding, _ = level
        for expr in holding:
            spans.append((start, end, expr))

    for number, raw_line in enumerate(lines):
        m = _DIRECTIVE_RE.match(raw_line)
        if m:
            directive, rest = m.group(1), m.group(2).strip()
            if directive in ("if", "ifdef", "ifndef"):
                if number in guard_lines:
                    # A header's own include guard wraps the entire file, so
                    # every declaration in every header would carry it -- 2,019
                    # of 3,568 preference and switch keys at M151, none of them
                    # a build condition. It is structure, not a guard.
                    stack.append([offset + len(raw_line), [], []])
                    offset += len(raw_line)
                    continue
                expr = rest
                if directive == "ifdef":
                    expr = f"defined({rest})"
                elif directive == "ifndef":
                    expr = f"!defined({rest})"
                stack.append([offset + len(raw_line), [expr], [expr]])
            elif directive in ("elif", "else"):
                if stack:
                    close(stack[-1], offset)
                    seen = stack[-1][2]
                    # Reaching a later branch means every earlier one was
                    # false, and those conditions are part of this branch's
                    # guard. Dropping them read the `#else` of
                    # `#if BUILDFLAG(IS_ANDROID)` as unguarded, which is the
                    # branch Windows actually compiles.
                    holding = [f"!({e})" for e in seen]
                    if directive == "elif":
                        holding = holding + [rest]
                        seen = seen + [rest]
                    stack[-1] = [offset + len(raw_line), holding, seen]
            elif directive == "endif":
                if stack:
                    close(stack.pop(), offset)
        offset += len(raw_line)
    while stack:  # unterminated #if: treat as running to end of file
        close(stack.pop(), len(text))
    return spans


def enclosing_conditions(spans: List[Tuple[int, int, str]], index: int) -> List[str]:
    return [expr for start, end, expr in spans if start <= index < end]


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
