"""What to pull from Chromium, and why.

Each entry answers a question a downstream browser team actually asks during
an uprev.  Keeping the list declarative (rather than hard-coded inside each
extractor) means adding a new source of truth is a one-line change, and the
cost of a snapshot stays visible.

Sizes below are measured against M143 tarballs.
"""

from __future__ import annotations

from typing import List

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


def get_targets(name: str) -> List[FetchTarget]:
    if name not in TARGET_SETS:
        raise KeyError(f"unknown target set {name!r}; have {sorted(TARGET_SETS)}")
    return TARGET_SETS[name]()
