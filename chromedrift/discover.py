"""Find the vendor's own code inside a merged fork, without being told where.

A fork of this shape is taken from Chromium whole, then the vendor's own files
are placed **inside Chromium's directories** rather than beside them:

    chrome/browser/resources/settings/privacy_page/privacy_page-acme.html <- ours
    chrome/browser/resources/acme/acme_wallet.html                        <- ours
    ui/acme/views/toolbar.cc                                              <- ours

So "which files are ours" is not answerable from Chromium's layout, and after
enough years nobody remembers the full list. That is a problem for every other
analysis here: `vendor_markers` decides what the shadow analysis can see, and
the target list decides what is read at all. Both were being filled in from
memory.

This module answers it from the tree instead. It costs one `os.walk` over a
local checkout -- no network, no content reading in the default mode -- because
the two strongest signals are in the names:

  * a **directory** named after the vendor (`acme/`, `acmebrowser/`)
  * a **filename suffix** marking a vendor variant of an upstream file (`-acme`)

The second one matters more than it looks. It sits *inside* an upstream
directory, so no path prefix finds it, and it has no vendor symbol prefix
either -- it is Chromium's own component name with a suffix. Nothing in the
marker vocabulary caught it before this module existed.

Content scanning (for `#if defined(ACME_*)`) is available but off by
default: it reads every source file in the tree, which is minutes rather than
seconds, and the name-based signals already locate the directories worth
looking at.

`acme` above is a placeholder. This module ships no vendor vocabulary of its
own and never guesses one: the tokens are arguments, because a wrong guess does
not fail, it invents matches. Callers pass the names their fork actually uses.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .targets import get_targets, reaches, scope_of

SKIP_DIRS = {".git", "out", "node_modules", "__pycache__", "build", ".gradle"}

# Source and resource extensions worth reporting. A vendor .png is real but
# says nothing about the feature surface.
INTERESTING_EXTS = (".cc", ".h", ".mm", ".java", ".ts", ".js", ".html",
                    ".idl", ".mojom", ".json", ".json5", ".gn", ".gni",
                    ".grd", ".grdp", ".xml")

# Match any uppercase macro in a preprocessor condition, then filter by
# substring in Python. Encoding "contains one of these words" directly in the
# pattern needs a leading `[A-Z][A-Z0-9_]*`, which silently requires at least
# one character *before* the word -- so `ACME_CUSTOM_DOWNLOADS`, the most
# common shape, matched nothing while `X_ACME_Y` matched.
MACRO_RE = re.compile(r"#\s*(?:if|elif|ifdef)\s+.*?\b([A-Z][A-Z0-9_]{3,})\b")

BY_DIR = "vendor directory"
BY_NAME = "vendor filename suffix"
BY_MACRO = "vendor build flag inside an upstream file"


@dataclass
class Hit:
    path: str
    rule: str
    detail: str = ""


@dataclass
class DiscoveryReport:
    root: str
    hits: List[Hit] = field(default_factory=list)
    files_walked: int = 0
    macros: Counter = field(default_factory=Counter)
    scanned_content: bool = False

    def by_rule(self) -> Dict[str, int]:
        return dict(Counter(h.rule for h in self.hits).most_common())

    def vendor_dirs(self, depth: int = 4) -> Dict[str, int]:
        """Directories holding vendor files, truncated to a useful depth.

        These are the candidates for `path_markers` in the profile and for new
        entries in the target list -- the two places a forgotten path silently
        removes a whole surface from the analysis.
        """
        out: Counter = Counter()
        for hit in self.hits:
            parts = hit.path.split("/")[:-1]
            out["/".join(parts[:depth])] += 1
        return dict(out.most_common())

    def by_area(self) -> Dict[str, int]:
        out: Counter = Counter()
        for hit in self.hits:
            out[hit.path.split("/")[0]] += 1
        return dict(out.most_common())

    def suffixes_seen(self) -> Dict[str, int]:
        out: Counter = Counter()
        for hit in self.hits:
            if hit.rule == BY_NAME:
                out[hit.detail] += 1
        return dict(out.most_common())

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "files_walked": self.files_walked,
            "scanned_content": self.scanned_content,
            "hits": len(self.hits),
            "by_rule": self.by_rule(),
            "by_area": self.by_area(),
            "vendor_dirs": self.vendor_dirs(),
            "suffixes_seen": self.suffixes_seen(),
            "macros": dict(self.macros.most_common(40)),
            "paths": [h.path for h in self.hits],
        }


def _dir_is_vendor(rel_dir: str, tokens: Sequence[str]) -> Optional[str]:
    for part in rel_dir.split("/"):
        low = part.lower()
        for token in tokens:
            if low == token or low.startswith(token) or token in low:
                return part
    return None


def _name_is_vendor(filename: str, suffixes: Sequence[str]) -> Optional[str]:
    stem = filename
    for _ in range(2):  # foo-si.html.ts -> foo-si.html -> foo-si
        stem = os.path.splitext(stem)[0]
    for suffix in suffixes:
        if stem.endswith(suffix):
            return suffix
    return None


def scan(root: str, dir_tokens: Sequence[str] = (),
         file_suffixes: Sequence[str] = (),
         macro_words: Sequence[str] = (),
         scan_content: bool = False,
         log=lambda m: None) -> DiscoveryReport:
    """Walk a local fork checkout and report every file that looks vendor-owned.

    At least one marker is required. With none, the walk finds nothing and
    reports "no vendor files", which is indistinguishable from a fork that
    really has none -- the one wrong answer this module must not give.
    """
    if not dir_tokens and not file_suffixes:
        raise ValueError(
            "no vendor markers given: pass dir_tokens and/or file_suffixes. "
            "This tool ships no vendor vocabulary of its own, because a "
            "guessed marker invents matches instead of failing.")
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise NotADirectoryError(root)

    report = DiscoveryReport(root=root, scanned_content=scan_content)
    tokens = [t.lower() for t in dir_tokens]
    # A vendor's build flags are its own name shouted: `acme/` -> `ACME_*`.
    # Deriving them keeps one list to get right instead of two that drift.
    words = [w.upper() for w in (macro_words or dir_tokens)]

    for dirpath, dirnames, filenames in os.walk(root):
        # Sorted for the same reason extraction sorts: a walk that depends on
        # the filesystem gives two machines two answers.
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        filenames = sorted(filenames)
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        vendor_dir = _dir_is_vendor(rel_dir, tokens) if rel_dir else None

        for filename in filenames:
            if not filename.endswith(INTERESTING_EXTS):
                continue
            report.files_walked += 1
            rel = f"{rel_dir}/{filename}" if rel_dir else filename

            if vendor_dir:
                report.hits.append(Hit(rel, BY_DIR, vendor_dir))
                continue

            suffix = _name_is_vendor(filename, file_suffixes)
            if suffix:
                report.hits.append(Hit(rel, BY_NAME, suffix))
                continue

            if scan_content and filename.endswith((".cc", ".h", ".mm")):
                try:
                    with open(os.path.join(dirpath, filename), encoding="utf-8",
                              errors="replace") as fh:
                        found = MACRO_RE.findall(fh.read())
                except OSError:
                    continue
                ours = [m for m in found if any(w in m for w in words)]
                if ours:
                    report.macros.update(ours)
                    report.hits.append(Hit(rel, BY_MACRO, ours[0]))

    report.hits.sort(key=lambda h: h.path)
    log(f"  walked {report.files_walked} source files, {len(report.hits)} look ours")
    return report


def _readable_by_any_extractor(path: str) -> bool:
    """Would any extractor produce facts from this file, if it were fetched?

    Asked the way `run_on_tree` asks it, skips included. A vendor file under a
    test directory matches an extractor's filename rule and is then skipped
    during extraction, so counting it as fixable puts something on the worklist
    that adding a target would not fix -- the exact split this function exists
    to make.
    """
    from .extract import REGISTRY, _other_platform, _skip

    if _skip(path):
        return False
    matched = [n for n, applies, _ in REGISTRY if applies(path)]
    if _other_platform(path):
        from .extract import CROSS_PLATFORM_EXTRACTORS
        matched = [n for n in matched if n in CROSS_PLATFORM_EXTRACTORS]
    return bool(matched)


def uncovered_dirs(report: DiscoveryReport, target_set: str = "default",
                   min_files: int = 1) -> Tuple[List[Tuple[str, int]],
                                                List[Tuple[str, int]]]:
    """Vendor directories the target list does not reach, split by fixability.

    Two very different situations, and merging them produces a worklist where
    most entries cannot be acted on:

    * **fetchable** -- an extractor would read these, so the only thing missing
      is a line in `targets.py`. A vendor directory here is simply absent from
      every comparison, and nothing else in the output says so.
    * **unreadable** -- no extractor claims this file whatever we do. Native
      C++ UI, .grd strings, .gn files. Adding a target changes nothing; these
      are outside the tool's model and belong in the report's limits section
      instead. For a fork with a large native UI this is usually the bigger
      pile, and calling it "missing" would imply a fix that does not exist.
    """
    # Scope is asked here exactly as extraction and coverage ask it. This
    # module used to keep its own copy, which stopped at the first prefix that
    # matched. Nested targets have different filters -- `chrome/browser/ui/webui`
    # is fetched for .cc, `chrome/browser` for a dozen suffixes -- so a header
    # under the first is reached by the second, and stopping early answered
    # "not covered" for files already on disk. That turned into a worklist
    # telling you to add targets you already have.
    files, trees = scope_of(get_targets(target_set))

    fetchable: Counter = Counter()
    unreadable: Counter = Counter()
    for hit in report.hits:
        if reaches(hit.path, files, trees):
            continue
        directory = "/".join(hit.path.split("/")[:-1])
        if _readable_by_any_extractor(hit.path):
            fetchable[directory] += 1
        else:
            unreadable[directory] += 1
    return ([(d, n) for d, n in fetchable.most_common() if n >= min_files],
            [(d, n) for d, n in unreadable.most_common() if n >= min_files])


def suggest_profile(report: DiscoveryReport) -> str:
    """A vendor_markers block filled in from what the tree actually contains."""
    dirs = sorted({h.detail for h in report.hits if h.rule == BY_DIR})
    suffixes = sorted(report.suffixes_seen())
    macros = [m for m, _ in report.macros.most_common(12)]
    lines = ["  vendor_markers: {"]
    if macros:
        lines.append("    macros: [" + ", ".join(f'"{m}"' for m in macros) + "],")
    else:
        lines.append("    // macros: run again with --scan-content to fill these")
    # Chromium's own convention is `kName`, so a vendor's variables are
    # `k<Vendor>...`. Derived from the directories actually found rather than
    # from a list, which is the same guess this module refuses to make.
    prefixes = [f"k{d[:1].upper()}{d[1:].lower()}" for d in dirs] or ["kVendor"]
    lines.append("    symbol_prefixes: ["
                 + ", ".join(f'"{p}"' for p in sorted(set(prefixes)))
                 + "],  // verify by hand")
    if dirs:
        lines.append("    path_markers: ["
                     + ", ".join(f'"{d.lower()}/"' for d in dirs) + "],")
    if suffixes:
        lines.append("    filename_markers: ["
                     + ", ".join(f'"{s}"' for s in suffixes) + "],")
    lines.append("  },")
    return "\n".join(lines)


def summarize(report: DiscoveryReport, limit: int = 20) -> List[str]:
    lines = [
        f"{report.files_walked:,} source files under {report.root}",
        f"{len(report.hits):,} look vendor-owned:",
    ]
    for rule, n in report.by_rule().items():
        lines.append(f"  {n:6,}  {rule}")

    suffixes = report.suffixes_seen()
    if suffixes:
        lines.append("")
        lines.append("filename suffixes in use:")
        for suffix, n in suffixes.items():
            lines.append(f"  {n:6,}  *{suffix}.*")

    areas = report.by_area()
    if areas:
        lines.append("")
        lines.append("by top-level directory:")
        for area, n in list(areas.items())[:limit]:
            lines.append(f"  {n:6,}  {area}/")

    if report.macros:
        lines.append("")
        lines.append("vendor build flags found:")
        for macro, n in report.macros.most_common(limit):
            lines.append(f"  {n:6,}  {macro}")
    return lines
