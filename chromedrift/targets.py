"""What to pull from Chromium, and why.

Each entry answers a question someone actually asks during
an uprev.  Keeping the list declarative (rather than hard-coded inside each
extractor) means adding a new source of truth is a one-line change, and the
cost of a snapshot stays visible.

Sizes below are measured against M143 tarballs.
"""

from __future__ import annotations

import re

from typing import Dict, List, Optional, Sequence

from .acquire import FetchTarget
from .extract._cpp import PLATFORM_DIR_RE
from .extract.webui_gates import WEBUI_HANDLER_DIR

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
# chrome/browser/resources/; these are the user-facing ones a desktop
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


# ---------------------------------------------------------------------------
# Discovery rules: say what to look for, not where it was last time
#
# A named list of files is only ever correct for the version it was written
# against. Measured by building the list as it would have stood at M130 and
# running it against M151, twenty-one milestones later:
#
#     pref files       293 -> 346    96 new, 43 gone   27% of M151 missed
#     feature files    516 -> 631   216 new, 101 gone  34% of M151 missed
#
# Curation loses roughly a third of its coverage over two years, silently, and
# the loss is invisible from inside a run: a file nobody listed is a file
# nobody notices. This project has already been bitten by that twice, and the
# fix both times was to add more names, which only resets the clock.
#
# So the targets below declare a *rule* -- these roots, this filename shape --
# and it is resolved against the actual tree of the version being read.
# Gitiles answers a full recursive listing per root in one request
# (`?format=JSON&recursive=true`), so all twelve roots cost about 24 MB and 21
# seconds on a cold cache, against the ~40 MB of source the same run already
# downloads. A tag's tree is immutable, so the listing is cached forever.
#
# The rules stay narrow on purpose. They are matched against filenames, which
# is a convention rather than a guarantee, so `chromedrift catalog` still
# exists to measure what the conventions themselves miss.
# ---------------------------------------------------------------------------

# The roots the coverage measurement looks in. Listing a root costs one
# request; listing all of Chromium would cost ~90 MB, which is why this is a
# list rather than "/".
#
# It is a list, so it is a *denominator you choose*, and that is exactly how a
# coverage number learns to flatter itself. These roots used to be the fourteen
# the fetch targets happen to live under, which meant the measurement graded
# `wide` against the ground `wide` already covered: 1,039 of 1,039, reported as
# **100%**, while `chromedrift catalog` -- which walks the real tree -- counted
# 1,192 files the same rule says can declare. The 153 in the gap could never
# show up as missed however wide the run, and they are not obscure:
# `base/base_switches.h`, `base/features.cc`, `cc/base/features.cc` (the
# compositor), `device/fido/public/features.cc` (WebAuthn),
# `sandbox/policy/features.cc`, `google_apis/gaia/gaia_switches.cc`,
# `storage/browser/quota/quota_features.cc`. Three of those files alone hold 88
# base::Feature declarations that no target set reads.
#
# This is the same defect schema 18 fixed one level down, where the measurement
# left `*flags.{cc,h}` out of its own denominator. There it was the filename
# rule that was too narrow; here it was the ground the rule ran over.
#
# So the roots now cover the tree rather than the fetch list. **They do not
# change what is downloaded** -- `discover_candidates` feeds the measurement
# only, never `get_targets` -- so the effect is that a gap which was invisible
# is now counted and named. Measured at M151: 18 more roots, 101,139 more
# listing entries, 15 seconds on a cold run and nothing on a warm one, since a
# tag's listing is cached forever.
DISCOVERY_ROOTS = (
    # `chrome` rather than three subdirectories of it: the three missed
    # `chrome/renderer`, `chrome/services` and `chrome/utility`, and one
    # listing of the parent is cheaper than three of its children anyway.
    "chrome", "components", "content", "extensions", "services",
    "net", "ui", "media", "printing", "gpu",
    # `third_party/blink` rather than its `public` and `common` subdirectories:
    # `renderer` holds 37 candidate files and was outside the measurement.
    "third_party/blink",
    # The roots that were missing outright. Between them they hold 102 of the
    # 153 files the measurement could not see.
    "base", "device", "cc", "google_apis", "sandbox", "storage", "pdf",
    "mojo", "apps", "crypto", "gin", "skia", "url", "dbus",
)

# Test code declares features and prefs that drive the test and ship to nobody.
_TEST_RE = re.compile(
    r"(unittest|browsertest|_test\.|_test_|/test/|/tests/|/testing/|test_util|"
    r"fuzzer|_mock\.|/mock/)")

# Platforms this product does not build. Reading them is not merely wasted --
# a ChromeOS-only declaration scores and sorts alongside real findings. The
# rule lives in `_cpp` because three stages ask it and two of them used to ask
# their own copy.
_OTHER_PLATFORM_RE = PLATFORM_DIR_RE

# Binaries that are not the product. content_shell is Chromium's test browser;
# its switches are real declarations that ship to nobody, so counting them as
# uncovered would make the coverage figure chase something worth ignoring.
# `headless/` is the headless shell, `remoting/` is Chrome Remote Desktop, and
# `chrome/updater`, `chrome/enterprise_companion` and `chrome/windows_services`
# are separate binaries that ship beside the browser rather than being it. Their
# switches are real declarations that reach none of our users, so counting them
# as uncovered would make the coverage figure chase 11 MB of downloads for
# fourteen files nobody here can act on.
_NOT_THE_PRODUCT_RE = re.compile(
    r"^content/shell/|^chrome/test/|^tools/|^headless/|^remoting/"
    r"|^chrome/(updater|enterprise_companion|windows_services)/")

# Vendored third-party projects. abseil, grpc, ipcz, libxml, opus, tflite, zlib
# and the webrtc overrides all carry files whose names match the conventions
# above -- 14 at M151 -- but they are other people's libraries, not Chromium's
# product surface, and no extractor is written for their dialects.
#
# Named here rather than left to fall outside the roots, because those are two
# different things. A file outside the roots is one the measurement cannot see;
# a file excluded here is one both the measurement and `catalog` agree to leave
# out, so the two describe the same population and the exclusion is reviewable.
# Blink is Chromium's own and stays in.
_VENDORED_THIRD_PARTY_RE = re.compile(r"^third_party/(?!blink/)")

# Preference keys. Chromium spells these two ways and both carry keys:
# `*pref_names.{h,cc}` is the older, larger set, `*_prefs.{h,cc}` the newer
# per-component one.
_PREF_FILE_RE = re.compile(
    r"(^|/)([a-z0-9_]*pref_names|[a-z0-9_]*_prefs|prefs)\.(h|cc)$")

# Feature flags and command-line switches. The convention is strong but not a
# rule, which is what `catalog` measures.
_FEATURE_FILE_RE = re.compile(
    r"(^|/)[a-z0-9_]*(features|switches|feature_list|field_trial|fieldtrial"
    r"|flags)\.(cc|h)$")


class DiscoveryRule:
    """Files to fetch, named by shape instead of by path."""

    __slots__ = ("pattern", "roots", "note")

    def __init__(self, pattern, roots=DISCOVERY_ROOTS, note=""):
        self.pattern = pattern
        self.roots = roots
        self.note = note

    def matches(self, path: str, include_other_platforms: bool = False) -> bool:
        if _TEST_RE.search(path) or _NOT_THE_PRODUCT_RE.search(path):
            return False
        if _VENDORED_THIRD_PARTY_RE.search(path):
            return False
        if not include_other_platforms and _OTHER_PLATFORM_RE.search(path):
            return False
        return bool(self.pattern.search(path))


DISCOVERY_RULES = (
    DiscoveryRule(_PREF_FILE_RE, note="preference keys"),
    DiscoveryRule(_FEATURE_FILE_RE, note="feature flags and switches"),
)


def could_declare(path: str,
                  include_other_platforms: bool = False) -> Optional[str]:
    """What this file could declare, by its name, or None if nothing.

    The single definition of "is this file worth reading", used both by the
    coverage measured on every run and by `catalog`. They each had their own
    before, written at different times, and they disagreed on 320 of the
    roughly 1,000 files in the M151 tree: catalog had never heard of the
    `*_prefs.{h,cc}` convention that holds 469 keys, and its platform filter
    only matched a leading `android/`, so it counted `chrome/browser/android/`
    as well. catalog is meant to be the authority on what is missing, which
    makes it the worst place to disagree with the number each run prints.
    """
    for rule in DISCOVERY_RULES:
        if rule.matches(path, include_other_platforms):
            return rule.note
    return None


def discover_candidates(source, log=lambda m: None) -> Dict[str, str]:
    """Every file in *this* version's tree that a rule says could declare.

    Discovery answers "what exists", not "what to fetch". Those turned out to
    be very different questions. Gitiles serves roughly one request per second
    per client whatever the concurrency -- measured at 8 and 16 threads it does
    not go faster, it starts refusing -- so pulling the ~1,000 files a rule
    matches costs about seventeen minutes per version and hammers a shared
    service to do it. The same content arrives as eleven directory archives in
    about three minutes.

    So fetching stays curated and cheap, and this exists to make the gap
    between the two *impossible to miss*: the count lands in every run's log
    and in the report, so a version that adds files moves a number a human
    reads, instead of quietly widening a hole nobody is looking at.
    """
    listings: Dict[str, List[str]] = {}
    for root in sorted({r for rule in DISCOVERY_RULES for r in rule.roots}):
        listings[root] = source.list_recursive(root)

    found: Dict[str, str] = {}
    for rule in DISCOVERY_RULES:
        hits = 0
        for root in rule.roots:
            for path in listings.get(root, ()):
                if rule.matches(path):
                    found.setdefault(path, rule.note)
                    hits += 1
        log(f"  {hits} file(s) in the tree could declare: {rule.note}")
    return found


def scope_of(targets: Sequence[FetchTarget]) -> tuple:
    """(exact files, [(tree prefix, suffix filter)]) a target set declares."""
    return ({t.path for t in targets if t.kind == "file"},
            [(t.path.rstrip("/") + "/", t.include)
             for t in targets if t.kind == "tree"])


def reaches(path: str, files, trees) -> bool:
    """Whether a declared scope reaches one path.

    Every prefix is tried, not just the first that matches. Nested targets are
    normal and their filters differ: `chrome/browser/ui/webui/` is declared for
    `.cc` while `chrome/browser/` is declared for a dozen suffixes, so a header
    under the former is reached by the latter. Stopping at the first prefix
    match answers "no" for 21 files that are on disk and read.

    One definition, because three modules were each carrying their own and two
    of them disagreed -- the same shape of bug as deriving fetch scope in one
    place and extraction scope in another.
    """
    if path in files:
        return True
    for prefix, include in trees:
        if not path.startswith(prefix):
            continue
        if not include or path.endswith(tuple(include)):
            return True
    return False


def coverage_against(candidates: Dict[str, str],
                     targets: Sequence[FetchTarget]) -> Dict[str, object]:
    """How much of what exists this target set actually reads."""
    files, trees = scope_of(targets)
    missed = sorted(p for p in candidates if not reaches(p, files, trees))
    by_dir: Dict[str, int] = {}
    for path in missed:
        top = "/".join(path.split("/")[:2])
        by_dir[top] = by_dir.get(top, 0) + 1
    return {
        "candidates": len(candidates),
        "read": len(candidates) - len(missed),
        "missed": len(missed),
        "missed_by_directory": dict(sorted(by_dir.items(), key=lambda kv: -kv[1])[:12]),
        "missed_paths": missed,
    }


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
        # Filtered by everything an extractor reads rather than by `.idl`
        # alone. These two archives are 21.5 MB and were already being
        # downloaded for their IDL, so the 22 feature and pref files inside
        # them went unread for want of a suffix in a filter -- the same thing
        # schema 17 found when 934 .mojom files were fetched and discarded.
        # Widening costs no bandwidth at all.
        FetchTarget("third_party/blink/renderer/modules", "tree",
                    READABLE_SUFFIXES, note="modules web IDL and declarations"),
        FetchTarget("third_party/blink/renderer/core", "tree",
                    READABLE_SUFFIXES, note="core web IDL and declarations"),

        # -- Mojo: the process-boundary ABI.  Any code that implements
        #    or calls a mojo interface breaks silently at runtime when a
        #    method signature moves, so signature-level diffing matters.
        FetchTarget("third_party/blink/public/mojom", "tree", _MOJOM,
                    note="blink mojo interfaces"),

        # -- Command-line switches and preferences: what integration scripts,
        #    automation and settings UI depend on.
        FetchTarget("content/public/common/content_switches.cc", "file"),
        # Discovery finds this too. It stays named because PARTITION_CORE
        # promises it to every partition, and a partitioned run filters the
        # static list -- so a core file that exists only as a discovery hit
        # would silently drop out of `--partition downloads`.
        FetchTarget("chrome/common/pref_names.h", "file",
                    note="pref keys; also core to every partition"),

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
        FetchTarget(GATE_ROOT, "tree", (".cc",),
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


# Whole-directory archives for what the curated list can only sample. One
# request each, filtered as they unpack. The measured effect is in
# `wide_targets` below; it is stated once so the two cannot disagree.
_WIDE_ROOTS = (
    ("components", "every components/ declaration"),
    ("chrome/browser", "every chrome/browser declaration, including all 132 "
                       "WebUI surfaces under resources/"),
    ("media", "every media/ declaration"),
    ("extensions", "every extensions/ declaration"),
    ("services", "every services/ declaration, including 252 Mojo interfaces"),
    ("net", "every net/ declaration"),
    ("ui", "every ui/ declaration"),
    ("gpu", "every gpu/ declaration"),
    ("printing", "every printing/ declaration"),
    ("chrome/common", "every chrome/common declaration"),
    # content/ cannot be fetched whole -- Gitiles answers 503 on an archive
    # that size -- so it is taken a level down. Together these are 15 MB and
    # carry 145 pref and 25 feature files the tool could not otherwise see.
    ("content/browser", "content/browser declarations"),
    ("content/common", "content/common declarations"),
    ("content/public", "content/public declarations"),
    ("content/renderer", "content/renderer declarations"),
    ("content/child", "content/child declarations"),
    ("content/services", "content/services declarations"),
    ("third_party/blink/common", "Blink's shared implementation declarations"),
    # The whole public surface, not just the mojom/ subdirectory.
    ("third_party/blink/public", "every Blink public declaration"),

    # -- The roots that closed the last 12%.
    #
    # `wide` used to read 1,039 of the 1,178 files the rule admits, and called
    # that 100% because the measurement graded it against the roots the fetch
    # list already lived under. Once the denominator became the tree, the 139
    # it was missing had names: base/, device/, cc/, sandbox/, storage/ and the
    # rest below. They are not obscure -- `base/base_switches.h` declares
    # --enable-logging and --v, `device/fido` is WebAuthn, `cc/base` is the
    # compositor, `google_apis/gaia` is sign-in -- and three of those files
    # alone hold 88 base::Feature declarations.
    #
    # Measured at M151 they cost 22 MB per version on top of 315, which is the
    # price of the figure meaning what it says.
    ("base", "base:: features, switches and field trials"),
    ("device", "Bluetooth, gamepad, VR and WebAuthn"),
    ("cc", "the compositor"),
    ("google_apis", "sign-in and GCM"),
    ("sandbox", "sandbox policy"),
    ("storage", "quota, blob and filesystem"),
    ("pdf", "the PDF viewer"),
    ("mojo", "Mojo core"),
    ("apps", "Chrome apps"),
    ("crypto", "crypto"),
    ("gin", "V8 bindings"),
    ("skia", "graphics"),
    ("url", "URL parsing"),
    # `core` and `modules` are already fetched by the default set; only
    # `platform` is a new download, at 5.8 MB.
    ("third_party/blink/renderer/platform", "Blink platform declarations"),
)

# Every filename shape an extractor can read, as basename suffixes.
#
# One tuple, because two fetch paths ask this same question -- a `wide` root and
# a `--complete` partition both download a whole archive and keep only the
# declarations out of it -- and answering it twice is how the two drift. They
# did: this list learned the `*_prefs.{h,cc}` convention when the extractor did,
# and the `--complete` copy did not, so the flag whose entire promise is "100%
# of these roots, by construction" skipped 86 files holding 747 keys at M151.
# The copy also carried `util.cc`, `handler.cc` and `manager.cc` in the bare
# spelling, which no extractor matches, so it fetched files nothing would read.
#
# Restricting it to feature and pref files was a gap hiding inside the answer
# to another one: the archives were already on disk, and the only reason 934 of
# the tree's 1,424 .mojom files and 124 of its 132 WebUI surfaces stayed unread
# was that their suffixes were missing here. Widening it costs no bandwidth at
# all.
# The one root whose rule is "every .cc" rather than a filename convention.
# Taken from the extractor that makes that claim, because the same directory
# was written out three times -- the extractor's rule, the default set's fetch
# target, and the --complete filter -- with nothing binding them. Chromium
# moves its WebUI directories; two of the three would move and the third would
# go quiet.
GATE_ROOT = WEBUI_HANDLER_DIR.rstrip("/")

READABLE_SUFFIXES = (
    # base_features: base::Feature, FeatureParam, command-line switches.
    # Bare and prefixed spellings both occur -- `switches.cc` as well as
    # `content_switches.cc` -- and `endswith` covers both from one entry.
    "features.cc", "features.h", "switches.cc", "switches.h",
    "feature_list.cc", "feature_list.h",
    "field_trial.cc", "field_trial.h", "fieldtrial.cc", "fieldtrial.h",
    "flags.cc", "flags.h",
    "_handler.cc", "_util.cc", "_manager.cc",
    # constants: preference keys, both naming conventions
    "pref_names.cc", "pref_names.h", "prefs.cc", "prefs.h",
    # mojom / web_idl / blink_runtime: the process boundary and the web platform
    ".mojom", ".idl", ".json5",
    # webui_routes / webui_controls: route tables and both template dialects
    "route.ts", "routes.ts", ".html", ".html.ts",
    # flags_metadata: chrome://flags expiry milestones
    "flag-metadata.json",
)


def wide_targets() -> List[FetchTarget]:
    """The default set, plus whole directories for what it can only sample.

    Much larger to fetch: about 315 MB per version against 40. The archives
    are filtered as they unpack, so the tree kept on disk is 94 MB against
    roughly 38. The real cost is bandwidth, once per version, and a tag is
    cached forever afterwards.

    Measured at M151, against a recursive listing of that version's own tree:
    the files read go from 42 of 1,039 to all 1,039, and base::Feature
    declarations from 2,062 to 3,951. These are the numbers as of that
    measurement -- every run prints its own, and that is the one to trust.
    """
    return default_targets() + [
        FetchTarget(root, "tree", READABLE_SUFFIXES, note=note)
        for root, note in _WIDE_ROOTS
    ]


TARGET_SETS = {
    "default": default_targets,
    "minimal": minimal_targets,
    "wide": wide_targets,
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

# What a complete fetch must include is the same question as what the tool can
# read, so it is answered once, by READABLE_SUFFIXES above.
#
# WebUI gates are the exception: `webui_gates.applies_to` claims every .cc
# under its handler directory, not a naming convention, so closing that root
# needs the suffix rather than the convention. The directory comes from the
# extractor -- see GATE_ROOT beside READABLE_SUFFIXES.

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
            include = READABLE_SUFFIXES
            if root == GATE_ROOT or root.startswith(GATE_ROOT + "/"):
                include = READABLE_SUFFIXES + (".cc",)
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
