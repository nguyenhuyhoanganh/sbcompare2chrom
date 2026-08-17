"""What to pull from Chromium, and why.

Each entry answers a question a downstream browser team actually asks during
an uprev.  Keeping the list declarative (rather than hard-coded inside each
extractor) means adding a new source of truth is a one-line change, and the
cost of a snapshot stays visible.

Sizes below are measured against M143 tarballs.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .acquire import FetchTarget

# Suffix filters keep the extracted tree small: the blink core tarball is
# ~15 MB compressed but we only care about .idl / .json5 / feature sources.
_CPP = (".cc", ".h")
_IDL = (".idl",)
_MOJOM = (".mojom",)
# Only the declarative parts of a WebUI surface: the templates that declare
# controls, and the route table that declares pages.  The rest of the
# TypeScript is behaviour, which this tool does not read.
_WEBUI_TEMPLATES = (".html", ".html.ts", "route.ts", "routes.ts")

# chrome:// surfaces worth tracking.  There are ~130 under
# chrome/browser/resources/; these are the user-facing ones a downstream
# browser normally ships and customizes.  Add a line to cover another.
WEBUI_SURFACES = (
    "settings",
    "history",
    "downloads",
    "bookmarks",
    "extensions",
    "password_manager",
    "new_tab_page",
    "print_preview",
)


def default_targets() -> List[FetchTarget]:
    """The standard target set (~40 MB per version)."""
    return [
        # -- base::Feature declarations: the canonical "what can be toggled"
        #    list.  A default-state flip here is the single highest-signal
        #    event in an uprev: it means a feature actually shipped.
        FetchTarget("content/public/common", "tree", _CPP,
                    "content layer features/switches"),
        # Blink splits these: the declarations live under public/, the
        # definitions (and therefore the default states) under common/.
        FetchTarget("third_party/blink/public/common/features.h", "file",
                    note="blink feature declarations"),
        FetchTarget("third_party/blink/common/features.cc", "file",
                    note="blink feature definitions"),
        FetchTarget("net/base/features.cc", "file", note="network stack"),
        FetchTarget("net/base/features.h", "file"),
        FetchTarget("media/base/media_switches.cc", "file", note="media"),
        FetchTarget("media/base/media_switches.h", "file"),
        FetchTarget("ui/base/ui_base_features.cc", "file", note="UI toolkit"),
        FetchTarget("ui/base/ui_base_features.h", "file"),
        FetchTarget("gpu/config/gpu_finch_features.cc", "file", note="GPU"),
        FetchTarget("gpu/config/gpu_finch_features.h", "file"),
        FetchTarget("services/network/public/cpp/features.cc", "file",
                    note="network service"),
        FetchTarget("services/network/public/cpp/features.h", "file"),
        FetchTarget("components/viz/common/features.cc", "file", note="viz/compositor"),
        FetchTarget("components/viz/common/features.h", "file"),
        FetchTarget("components/autofill/core/common/autofill_features.cc", "file"),
        FetchTarget("components/password_manager/core/common/"
                    "password_manager_features.cc", "file"),
        FetchTarget("components/safe_browsing/core/common/features.cc", "file"),
        FetchTarget("components/permissions/features.cc", "file"),
        FetchTarget("components/download/public/common/download_features.cc", "file"),

        # The list above started from the layers a browser embeds and missed
        # the browser's own.  Measured at M151, these files declare 964 more
        # base::Feature than the set above -- about 45% of the total, with
        # chrome_features.cc alone holding 247.  A gap that size does not
        # look like a gap in a report: it looks like a quiet uprev.
        FetchTarget("chrome/common/chrome_features.cc", "file",
                    note="Chrome-level features (247 at M151)"),
        FetchTarget("chrome/common/chrome_features.h", "file"),
        FetchTarget("content/common/features.cc", "file",
                    note="content internals (126)"),
        FetchTarget("components/omnibox/common/omnibox_features.cc", "file",
                    note="omnibox (101)"),
        FetchTarget("extensions/common/extension_features.cc", "file",
                    note="extensions (57)"),
        FetchTarget("components/sync/base/features.cc", "file", note="sync (47)"),
        FetchTarget("components/segmentation_platform/public/features.cc", "file"),
        FetchTarget("components/optimization_guide/core/"
                    "optimization_guide_features.cc", "file"),
        FetchTarget("components/search_engines/search_engines_switches.cc", "file"),
        FetchTarget("components/history/core/browser/features.cc", "file"),
        FetchTarget("components/bookmarks/common/bookmark_features.cc", "file"),
        FetchTarget("printing/printing_features.cc", "file"),
        FetchTarget("ui/views/views_features.cc", "file"),

        # -- Blink runtime features: the web-platform API surface, with an
        #    explicit stable/experimental/test status per platform.  This is
        #    the best single answer to "what web APIs changed for our users".
        FetchTarget("third_party/blink/renderer/platform/"
                    "runtime_enabled_features.json5", "file",
                    note="web platform feature status"),

        # -- Web IDL: exact API shape.  Diffing these catches removed methods
        #    (a compat break for sites) and new methods (adoption work).
        FetchTarget("third_party/blink/renderer/modules", "tree", _IDL,
                    note="modules web IDL"),
        FetchTarget("third_party/blink/renderer/core", "tree", _IDL,
                    note="core web IDL"),

        # -- Mojo: the process-boundary ABI.  Downstream code that implements
        #    or calls a mojo interface breaks silently at runtime when a
        #    method signature moves, so signature-level diffing matters.
        FetchTarget("third_party/blink/public/mojom", "tree", _MOJOM,
                    note="blink mojo interfaces"),

        # -- Command-line switches and preferences: what integration scripts,
        #    automation and settings UI depend on.
        FetchTarget("content/public/common/content_switches.cc", "file"),
        FetchTarget("chrome/common/pref_names.h", "file", note="pref keys"),

        # -- chrome://flags metadata: expiry milestones tell you which flags
        #    are scheduled for deletion, i.e. future forced work.
        FetchTarget("chrome/browser/flag-metadata.json", "file",
                    note="flag expiry milestones"),

        # -- Desktop WebUI surfaces.  Settings, History, Downloads, Bookmarks
        #    and Extensions are all web pages built the same way, so one set
        #    of extractors reads all of them.  Only the route tables and HTML
        #    templates are pulled, which keeps this to ~1.7 MB for all eight.
        *(FetchTarget(f"chrome/browser/resources/{surface}", "tree",
                      _WEBUI_TEMPLATES, note=f"chrome://{surface} UI")
          for surface in WEBUI_SURFACES),

        # -- The C++ side of those pages: where each loadTimeData key that
        #    guards a page gets its value, usually from a base::Feature.
        #    This is the middle hop between a page and the flag behind it.
        FetchTarget("chrome/browser/ui/webui", "tree", (".cc",),
                    note="WebUI handlers: loadTimeData -> feature"),
    ]


def minimal_targets() -> List[FetchTarget]:
    """Fast subset (~1 MB) for smoke tests and CI wiring checks."""
    return [
        FetchTarget("third_party/blink/renderer/platform/"
                    "runtime_enabled_features.json5", "file"),
        FetchTarget("content/public/common/content_features.cc", "file"),
        FetchTarget("content/public/common/content_switches.cc", "file"),
    ]


TARGET_SETS = {
    "default": default_targets,
    "minimal": minimal_targets,
}

# ---------------------------------------------------------------------------
# Partitions: bound what gets fetched and scanned, when you only care about one
# part of the product.
#
# These are filters over the target list above, not a second list to maintain,
# so a target added there flows into whichever partitions its path matches.
#
# The trade is real and one-directional: partitioning is faster and *less
# complete*. Chromium is not organized by product feature, so a change that
# affects downloads can live in content/, in a Mojo interface, or in a flag
# file that matches no partition at all. Measured on the area routing, product
# scoping alone left 81% of findings unassigned, including the most severe.
#
# Right for iterating on one surface. Wrong for a release-gate run, which
# should always use the full set.
# ---------------------------------------------------------------------------

# Cheap and relevant to everything, so every partition keeps them.
PARTITION_CORE = (
    "chrome/common/pref_names.h",
    "chrome/browser/flag-metadata.json",
    "content/public/common/content_switches.cc",
)

PARTITIONS = {
    "settings": (
        "chrome/browser/resources/settings",
        "chrome/browser/ui/webui",
        "chrome/common/chrome_features.cc",
        "chrome/common/chrome_features.h",
    ),
    "downloads": (
        "chrome/browser/resources/downloads",
        "components/download/",
    ),
    "bookmarks": (
        "chrome/browser/resources/bookmarks",
        "components/bookmarks/",
    ),
    "history": (
        "chrome/browser/resources/history",
        "components/history/",
    ),
    "extensions": (
        "chrome/browser/resources/extensions",
        "extensions/",
    ),
    "passwords": (
        "chrome/browser/resources/password_manager",
        "components/password_manager/",
    ),
    "printing": (
        "chrome/browser/resources/print_preview",
        "printing/",
    ),
    "newtab": (
        "chrome/browser/resources/new_tab_page",
    ),
    # Not a product surface, but the one that carries the severe findings:
    # Mojo and Web IDL belong to no feature and are easy to forget.
    "webplatform": (
        "third_party/blink/",
    ),
    "network": (
        "net/base/",
        "services/network/",
    ),
    "media": (
        "media/base/",
    ),
}


# ---------------------------------------------------------------------------
# Complete partitions: 100% of a bounded surface, by construction
#
# Filtering the curated list inherits the curation gap, so `--partition
# downloads` is only ever as complete as the hand-written list happens to be.
# Measured at M151, that leaves real holes in small partitions: bookmarks was
# missing `bookmark_pref_names.h`, history both of its pref files, downloads a
# Mojo interface.
#
# `--complete` inverts the derivation. Instead of filtering files someone chose,
# it pulls whole directory roots and lets the extractors decide what to read, so
# every declaration inside the roots is covered whether or not anyone thought of
# it. Coverage is then a property of the roots, which are reviewable, rather
# than of a list, which drifts.
#
# This is affordable only because the roots are small. Measured tarball sizes at
# M151: components/bookmarks 0.2 MB, components/download 0.4 MB,
# components/history 0.5 MB, net/base 0.7 MB, extensions/ 3.8 MB,
# chrome/browser/ui/webui 3.4 MB. Gitiles serves a whole directory or nothing,
# so a root like third_party/blink/ would be hundreds of megabytes -- which is
# why `webplatform` is not closable and says so instead of pretending.
# ---------------------------------------------------------------------------

# Every filename any extractor can read, as basename suffixes. Kept in one place
# because "what the tool can read" and "what a complete fetch must include" are
# the same question, and answering it twice is how they drift apart.
COMPLETE_SUFFIXES = (
    # base_features.FILE_HINTS
    "features.cc", "features.h", "switches.cc", "switches.h",
    "fieldtrial.cc", "field_trial.cc", "flags.cc", "feature_list.cc",
    "util.cc", "handler.cc", "manager.cc",
    # constants.py
    "pref_names.cc", "pref_names.h",
    # web_idl / mojom
    ".idl", ".mojom",
    # webui_controls / webui_routes
    ".html", ".html.ts", "route.ts", "routes.ts",
    # blink_runtime / flags_metadata
    ".json5", "flag-metadata.json",
)

# WebUI gates are the exception: `webui_gates.applies_to` claims every .cc under
# chrome/browser/ui/webui/, not a naming convention, so closing that root needs
# the suffix rather than the convention.
_GATE_ROOT = "chrome/browser/ui/webui"

# Partitions whose roots are small enough to fetch whole. The rest keep their
# curated targets; `--complete` on them is refused rather than silently ignored.
CLOSABLE = {
    "settings", "downloads", "bookmarks", "history", "extensions",
    "passwords", "printing", "newtab", "network", "media",
}


def _is_file(path: str) -> bool:
    """A path naming a file, not a directory, judged by its extension."""
    return "." in path.rsplit("/", 1)[-1]


def complete_targets(partitions: Sequence[str]) -> List[FetchTarget]:
    """Every readable file under the partitions' roots, plus the core files."""
    targets = [FetchTarget(p, "file", note="partition core")
               for p in PARTITION_CORE]
    seen = set(PARTITION_CORE)
    for partition in partitions:
        for root in PARTITIONS[partition]:
            root = root.rstrip("/")
            if root in seen:
                continue
            seen.add(root)
            if _is_file(root):
                targets.append(FetchTarget(root, "file", note=partition))
                continue
            include = COMPLETE_SUFFIXES
            if root == _GATE_ROOT or root.startswith(_GATE_ROOT + "/"):
                include = COMPLETE_SUFFIXES + (".cc",)
            targets.append(FetchTarget(root, "tree", include,
                                       note=f"{partition}: complete"))
    return targets


def get_targets(name: str, partitions: Optional[Sequence[str]] = None,
                complete: bool = False) -> List[FetchTarget]:
    if name not in TARGET_SETS:
        raise KeyError(f"unknown target set {name!r}; have {sorted(TARGET_SETS)}")
    if not partitions:
        if complete:
            raise ValueError("--complete needs at least one --partition; "
                             "there is no affordable closure over all of Chromium")
        return TARGET_SETS[name]()

    unknown = [p for p in partitions if p not in PARTITIONS]
    if unknown:
        raise KeyError(f"unknown partition(s) {unknown}; have {sorted(PARTITIONS)}")

    if complete:
        not_closable = sorted(set(partitions) - CLOSABLE)
        if not_closable:
            raise ValueError(
                f"partition(s) {not_closable} cannot be fetched completely: "
                f"their roots are whole Chromium subsystems and Gitiles serves a "
                f"directory or nothing. Run them without --complete, or narrow "
                f"the roots in targets.py. Closable: {sorted(CLOSABLE)}")
        return complete_targets(partitions)

    prefixes = tuple(PARTITION_CORE)
    for partition in partitions:
        prefixes += PARTITIONS[partition]
    return [t for t in TARGET_SETS[name]() if t.path.startswith(prefixes)]


def partition_names() -> List[str]:
    return sorted(PARTITIONS)
