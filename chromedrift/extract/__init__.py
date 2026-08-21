"""Extractor registry.

An extractor is a pair of pure functions: ``applies_to(rel_path) -> bool`` and
``extract(text, rel_path) -> [Fact]``.  Keeping them pure and path-driven means
adding a source of truth is a one-line registration, and every extractor can be
unit-tested against a string with no network and no checkout.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..eligibility import in_scope
from ..model import Fact, dedupe_facts
from ._cpp import PLATFORM, other_platform_dir
from . import (
    base_features,
    blink_runtime,
    constants,
    flags_metadata,
    mojom,
    web_idl,
    webui_controls,
    webui_gates,
    webui_routes,
)

Extractor = Tuple[str, Callable[[str], bool], Callable[[str, str], List[Fact]]]

REGISTRY: List[Extractor] = [
    ("base_features", base_features.applies_to, base_features.extract),
    ("blink_runtime", blink_runtime.applies_to, blink_runtime.extract),
    ("web_idl", web_idl.applies_to, web_idl.extract),
    ("mojom", mojom.applies_to, mojom.extract),
    ("constants", constants.applies_to, constants.extract),
    ("flags_metadata", flags_metadata.applies_to, flags_metadata.extract),
    ("webui_routes", webui_routes.applies_to, webui_routes.extract),
    ("webui_controls", webui_controls.applies_to, webui_controls.extract),
    ("webui_gates", webui_gates.applies_to, webui_gates.extract),
]

# Generated output and test code: noise for every extractor, always.
SKIP_DIR_PARTS = (
    "/testing/", "/test/", "/tests/", "/out/", "/.git/", "/__pycache__/",
    "/fuzzers/", "/fuzzer/", "/web_test/", "/web_tests/",
)

# ...and the ones that are test code by filename rather than by directory.
# The directory list alone let 151 facts at M151 into a product report from
# `network_service_test.mojom`, `fuzz.mojom` and `usb_manager_test.mojom` --
# interfaces that exist to drive a test and ship to nobody. A change in one
# would be presented as a moved product contract, at Mojo severity.
SKIP_FILE_RE = re.compile(
    r"(^|/)[^/]*(_test|_unittest|_browsertest|_fuzzer|_test_api)\.[a-z0-9]+$"
    r"|(^|/)fuzz\.mojom$")

# Platforms a Windows desktop browser never compiles. Their features, web APIs
# and UI say nothing about this product.
OTHER_PLATFORM_PARTS = ("/chromeos/", "/ash/", "/ios/", "/fuchsia/")

# ...with one exception, and it is not a loophole but the point.
#
# A pref key is identified by its string, and Chromium is splitting
# chrome/common/pref_names.h apart. When a key moves out of it into a ChromeOS
# file, a reader that cannot see the destination has only two categories for
# what it observes -- deleted, or moved -- and no way to tell them apart. It
# reports a deletion, which for a pref means every existing user's stored value
# is orphaned. Measured M148 -> M151: of 141 keys that vanished, 100 had simply
# moved into a ChromeOS pref file.
#
# So string constants are read wherever they live. They are cheap, they carry
# no platform behaviour, and having them turns a wrong answer into a right one.
# The profile's ignore_paths scores anything under those trees down; being
# visible is not the same as being important.
CROSS_PLATFORM_EXTRACTORS = ("constants",)


def _skip(rel_path: str) -> bool:
    """Out of scope, by the one policy discovery also uses."""
    return not in_scope(rel_path.replace(os.sep, "/"))


def _other_platform(rel_path: str) -> bool:
    probe = "/" + rel_path.replace(os.sep, "/") + "/"
    return any(part in probe for part in OTHER_PLATFORM_PARTS)


def _in_scope(rel_path: str, allow_paths: Optional[Set[str]],
              allow_prefixes) -> bool:
    """True when this file belongs to the declared target set.

    A tree target carries a suffix filter as well as a path, and the scope has
    to honour both.  Matching on the path alone lets a file the target never
    asked for be extracted anyway, purely because an earlier run left it in the
    shared per-ref tree cache -- and the two sides of a comparison rarely have
    the same leftovers, so the difference reads as a mass deletion.

    Measured on M148 -> M151: the ``chrome/browser/ui/webui`` target asks for
    ``.cc`` only, but a previous ``--partition settings --complete`` run had
    left 103 ``.mojom`` files under that prefix in the M148 tree and none in
    the M151 one.  Prefix-only scoping read all 103, producing **803 phantom
    "Mojo method removed" findings** -- the highest-severity signal the tool
    has, at the top of the report, describing nothing.
    """
    from ..targets import reaches

    if allow_paths is None and allow_prefixes is None:
        return True  # unscoped: caller wants everything present
    return reaches(rel_path, allow_paths or set(), _as_pairs(allow_prefixes))


def _as_pairs(allow_prefixes):
    """Accept either ``{prefix: include}`` or a bare set of prefixes."""
    if not allow_prefixes:
        return ()
    if isinstance(allow_prefixes, dict):
        return tuple(allow_prefixes.items())
    return tuple((p, None) for p in allow_prefixes)


def run_on_tree(root: str, log=lambda m: None, skip_dirs: bool = True,
                allow_paths: Optional[Set[str]] = None,
                allow_prefixes=None
                ) -> Tuple[List[Fact], Dict[str, int]]:
    """Walk a materialized partial checkout and run every matching extractor.

    ``allow_paths`` / ``allow_prefixes`` scope extraction to what the caller's
    target set actually declared.  ``allow_prefixes`` may be a bare set of path
    prefixes, or a ``{prefix: suffix_filter}`` mapping -- the mapping form is
    what keeps a tree target's filter in force, see ``_in_scope``.  Without that scoping, extraction silently
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
    # Uids seen at least once outside a platform directory. Chromium declares
    # the same key in both places five times at M151 -- all of them the generic
    # fragments `pref:id`, `pref:name`, `pref:system` -- and dedupe keeps the
    # lowest path, which is the ChromeOS one. Stamping per file would mark
    # those five as not ours on the strength of a copy we do not build.
    ours_somewhere: Set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        # Sorted, like the filenames below already were. os.walk hands back
        # directories in filesystem order, which differs between machines and
        # between the two trees of one comparison -- and when two files declare
        # the same fact, the order decides which one is kept. Measured on the
        # M151 tree: walking it twice in different orders and diffing the result
        # against itself produced 68 changes out of nothing, the largest a
        # `web_api_signature_change` at severity 50.
        dirnames[:] = sorted(d for d in dirnames
                             if d not in (".git", "__pycache__", ".chromedrift"))
        for filename in sorted(filenames):
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root).replace(os.sep, "/")
            if skip_dirs and _skip(rel_path):
                continue
            if not _in_scope(rel_path, allow_paths, allow_prefixes):
                continue
            matched = [(n, fn) for n, applies, fn in REGISTRY if applies(rel_path)]
            other_platform = other_platform_dir(rel_path)
            if skip_dirs and _other_platform(rel_path):
                # Not this platform's code, so only the extractors that exist to
                # answer "where did this string go" still run.
                matched = [m for m in matched
                           if m[0] in CROSS_PLATFORM_EXTRACTORS]
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
                if not other_platform:
                    ours_somewhere.update(f.uid for f in produced)

    stats["_files"] = files_seen
    stats["_errors"] = errors
    return dedupe_facts(_stamp_platform_dirs(facts, ours_somewhere)), stats


def _stamp_platform_dirs(facts: List[Fact], ours_somewhere: Set[str]) -> List[Fact]:
    """Mark what a platform directory keeps out of our binary.

    Chromium excludes these directories in BUILD.gn, not with a preprocessor
    guard, so nothing inside `chrome/browser/ash/` carries an
    `#if BUILDFLAG(IS_CHROMEOS)` for `resolve_platform_state` to find. The path
    is the only evidence there is, and it decides the same thing a guard does,
    so it is written into the same attribute rather than a second one the
    scoring stage would also have to learn.

    Only when *every* declaration of the uid is under such a directory --
    the rule `score._not_in_build` already applies across the two sides of a
    change, applied here across the places one fact is declared.
    """
    for fact in facts:
        if fact.uid in ours_somewhere or not other_platform_dir(fact.path):
            continue
        fact.attrs["platform_state"] = dict(fact.attrs.get("platform_state") or {},
                                            **{PLATFORM: "not_compiled"})
    return facts


def extractor_names() -> List[str]:
    return [name for name, _, _ in REGISTRY]
