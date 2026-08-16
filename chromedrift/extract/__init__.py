"""Extractor registry.

An extractor is a pair of pure functions: ``applies_to(rel_path) -> bool`` and
``extract(text, rel_path) -> [Fact]``.  Keeping them pure and path-driven means
adding a source of truth is a one-line registration, and every extractor can be
unit-tested against a string with no network and no checkout.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..model import Fact, dedupe_facts
from . import base_features, blink_runtime, constants, flags_metadata, mojom, web_idl

Extractor = Tuple[str, Callable[[str], bool], Callable[[str, str], List[Fact]]]

REGISTRY: List[Extractor] = [
    ("base_features", base_features.applies_to, base_features.extract),
    ("blink_runtime", blink_runtime.applies_to, blink_runtime.extract),
    ("web_idl", web_idl.applies_to, web_idl.extract),
    ("mojom", mojom.applies_to, mojom.extract),
    ("constants", constants.applies_to, constants.extract),
    ("flags_metadata", flags_metadata.applies_to, flags_metadata.extract),
]

# Directories that only add noise: generated output, tests and platform trees a
# mobile browser never compiles.
SKIP_DIR_PARTS = (
    "/testing/", "/test/", "/tests/", "/out/", "/.git/", "/__pycache__/",
    "/chromeos/", "/ash/", "/ios/", "/fuchsia/",
)


def _skip(rel_path: str) -> bool:
    probe = "/" + rel_path.replace(os.sep, "/") + "/"
    return any(part in probe for part in SKIP_DIR_PARTS)


def _in_scope(rel_path: str, allow_paths: Optional[Set[str]],
              allow_prefixes: Optional[Set[str]]) -> bool:
    """True when this file belongs to the declared target set."""
    if allow_paths is None and allow_prefixes is None:
        return True  # unscoped: caller wants everything present
    if allow_paths and rel_path in allow_paths:
        return True
    if allow_prefixes and any(rel_path.startswith(p) for p in allow_prefixes):
        return True
    return False


def run_on_tree(root: str, log=lambda m: None, skip_dirs: bool = True,
                allow_paths: Optional[Set[str]] = None,
                allow_prefixes: Optional[Set[str]] = None
                ) -> Tuple[List[Fact], Dict[str, int]]:
    """Walk a materialized partial checkout and run every matching extractor.

    ``allow_paths`` / ``allow_prefixes`` scope extraction to what the caller's
    target set actually declared.  Without that scoping, extraction silently
    takes its scope from whatever happens to be on disk -- and since the tree
    cache is shared per ref across target sets, running ``--target-set minimal``
    in a directory a previous ``default`` run had populated produced a
    "minimal" snapshot containing the full 21,595 facts.  Diffed against a real
    minimal snapshot, that invented roughly 20,000 phantom additions and looked
    entirely plausible.
    """
    facts: List[Fact] = []
    stats: Dict[str, int] = {name: 0 for name, _, _ in REGISTRY}
    files_seen = 0
    errors = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", ".chromedrift")]
        for filename in sorted(filenames):
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root).replace(os.sep, "/")
            if skip_dirs and _skip(rel_path):
                continue
            if not _in_scope(rel_path, allow_paths, allow_prefixes):
                continue
            matched = [(n, fn) for n, applies, fn in REGISTRY if applies(rel_path)]
            if not matched:
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                errors += 1
                continue
            files_seen += 1
            for name, fn in matched:
                try:
                    produced = fn(text, rel_path)
                except Exception as exc:  # one bad file must not kill a snapshot
                    errors += 1
                    log(f"    ! {name} failed on {rel_path}: {exc}")
                    continue
                stats[name] += len(produced)
                facts.extend(produced)

    stats["_files"] = files_seen
    stats["_errors"] = errors
    return dedupe_facts(facts), stats


def extractor_names() -> List[str]:
    return [name for name, _, _ in REGISTRY]
