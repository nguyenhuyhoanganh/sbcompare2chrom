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


# ---------------------------------------------------------------------------
# Preference keys, the rest of them
#
# A pref key is a contract with data already on the user's disk: rename one and
# every existing profile's stored value is orphaned, silently, while the code
# still builds and the tests still pass. So the cost of not reading a pref file
# is not a smaller report -- it is a class of silent breakage the tool claims
# to cover and does not.
#
# For a long time the list below was a single entry, chrome/common/pref_names.h,
# and that looked sufficient because it is by far the biggest one. It is not:
# Chromium has been splitting it apart for years (4,322 lines at M143, 3,267 at
# M151), and the keys leaving it land in per-component files.
#
# Measured at M151 by enumerating every `*pref_names.{h,cc}` in the tree and
# reading each one:
#
#     144 candidate files (excluding ChromeOS, iOS, WebView, Cast)
#      87 of them actually declare keys
#   1,575 keys in total
#     683 of those in chrome/common/pref_names.h  -- what we used to read
#     892 in the other 86 files                   -- what we used to miss
#
# The whole set is 366 KB, against roughly 40 MB already fetched per version,
# so completeness here costs about half a percent. Before this, 337 of those
# moves showed up across M143 -> M148 -> M151 as keys "disappearing", which is
# what the pref_left_scan signal exists to describe honestly.
#
# Counts in the trailing comments are keys at M151. Regenerate the list with
# `chromedrift catalog <ref>`, which measures this gap directly.
#
# Chromium uses *two* naming conventions for these files, and reading only the
# first is how the count above still came up short. `*pref_names.{h,cc}` is the
# older set; `*_prefs.{h,cc}` is what per-component keys use now. Measured at
# M151 the second convention holds another 469 keys across 54 files -- Memory
# Saver, Safety Hub, signin, enterprise connectors -- so the two lists below are
# both needed and the extractor recognises both spellings.
# ---------------------------------------------------------------------------

PREF_FILES = (
    "chrome/browser/accessibility/tree_fixing/pref_names.h",                  # 1
    "chrome/browser/desktop_to_mobile_promos/promos_pref_names.h",            # 23
    "chrome/browser/finds/core/finds_pref_names.cc",                          # 5
    "chrome/browser/first_party_sets/first_party_sets_pref_names.cc",         # 1
    "chrome/browser/glic/glic_pref_names.h",                                  # 32
    "chrome/browser/media/prefs/pref_names.cc",                               # 2
    "chrome/browser/metrics/profile_pref_names.cc",                           # 5
    "chrome/browser/new_tab_page/ntp_pref_names.h",                           # 17
    "chrome/browser/pdf/pdf_pref_names.cc",                                   # 5
    "chrome/browser/prefetch/pref_names.cc",                                  # 3
    "chrome/browser/screen_ai/pref_names.cc",                                 # 1
    "chrome/browser/signin/chrome_signin_pref_names.h",                       # 14
    "chrome/browser/ui/tabs/saved_tab_groups/saved_tab_group_pref_names.h",   # 6
    "chrome/browser/ui/toolbar/toolbar_pref_names.h",                         # 5
    "chrome/browser/webauthn/webauthn_pref_names.cc",                         # 7
    "chrome/browser/win/installer_downloader/installer_downloader_pref_names.h",# 4
    "components/account_manager_core/pref_names.cc",                          # 3
    "components/blocked_content/pref_names.cc",                               # 1
    "components/bookmarks/common/bookmark_pref_names.h",                      # 10
    "components/browsing_data/core/pref_names.h",                             # 17
    "components/certificate_transparency/pref_names.cc",                      # 2
    "components/collaboration/public/pref_names.cc",                          # 1
    "components/commerce/core/pref_names.h",                                  # 8
    "components/component_updater/pref_names.cc",                             # 3
    "components/content_settings/core/common/pref_names.h",                   # 109
    "components/contextual_search/pref_names.h",                              # 2
    "components/custom_handlers/pref_names.cc",                               # 5
    "components/desktop_to_mobile_promos/pref_names.h",                       # 3
    "components/device_signals/core/browser/pref_names.cc",                   # 3
    "components/dom_distiller/core/pref_names.h",                             # 5
    "components/drive/drive_pref_names.h",                                    # 11
    "components/embedder_support/origin_trials/pref_names.cc",                # 3
    "components/embedder_support/pref_names.h",                               # 1
    "components/enterprise/browser/reporting/common_pref_names.cc",           # 18
    "components/enterprise/content/pref_names.cc",                            # 4
    "components/enterprise/idle/idle_pref_names.cc",                          # 6
    "components/feature_engagement/public/pref_names.h",                      # 1
    "components/feed/core/common/pref_names.cc",                              # 21
    "components/feed/core/shared_prefs/pref_names.cc",                        # 3
    "components/history/core/common/pref_names.cc",                           # 2
    "components/language/core/browser/pref_names.h",                          # 8
    "components/live_caption/pref_names.h",                                   # 14
    "components/media_router/common/pref_names.cc",                           # 5
    "components/metrics/dwa/dwa_pref_names.cc",                               # 3
    "components/metrics/metrics_pref_names.h",                                # 48
    "components/metrics/private_metrics/private_metrics_pref_names.h",        # 2
    "components/network_time/network_time_pref_names.cc",                     # 2
    "components/ntp_tiles/pref_names.h",                                      # 20
    "components/omnibox/browser/omnibox_pref_names.h",                        # 29
    "components/on_device_translation/public/pref_names.cc",                  # 3
    "components/onc/onc_pref_names.cc",                                       # 2
    "components/password_manager/core/common/password_manager_pref_names.h",  # 46
    "components/permissions/pref_names.cc",                                   # 6
    "components/policy/core/browser/url_list/url_list_policy_pref_names.h",   # 4
    "components/policy/core/common/policy_pref_names.h",                      # 44
    "components/proxy_config/proxy_config_pref_names.h",                      # 6
    "components/quirks/pref_names.cc",                                        # 1
    "components/reading_list/core/reading_list_pref_names.cc",                # 1
    "components/safety_check/safety_check_pref_names.h",                      # 1
    "components/saved_tab_groups/public/pref_names.h",                        # 17
    "components/search_engines/search_engines_pref_names.h",                  # 17
    "components/security_interstitials/core/pref_names.cc",                   # 2
    "components/send_tab_to_self/pref_names.cc",                              # 2
    "components/sharing_message/pref_names.h",                                # 4
    "components/signin/public/base/signin_pref_names.cc",                     # 41
    "components/site_engagement/core/pref_names.cc",                          # 1
    "components/site_isolation/pref_names.cc",                                # 2
    "components/spellcheck/browser/pref_names.h",                             # 7
    "components/supervised_user/core/common/pref_names.h",                    # 24
    "components/sync/base/pref_names.h",                                      # 40
    "components/sync_preferences/cross_device_pref_tracker/prefs/cross_device_pref_names.h",# 8
    "components/themes/pref_names.h",                                         # 1
    "components/tracing/common/pref_names.cc",                                # 1
    "components/translate/core/browser/translate_pref_names.h",               # 7
    "components/ukm/ukm_pref_names.cc",                                       # 3
    "components/unified_consent/pref_names.cc",                               # 2
    "components/user_manager/user_manager_pref_names.h",                      # 18
    "components/variations/pref_names.h",                                     # 28
    "components/web_resource/web_resource_pref_names.cc",                     # 1
    "components/webui/chrome_urls/pref_names.h",                              # 1
    "components/webui/flags/flags_ui_pref_names.cc",                          # 2
    "extensions/browser/api/audio/pref_names.cc",                             # 1
    "extensions/browser/extension_pref_names.h",                              # 7
    "extensions/browser/pref_names.h",                                        # 33
    "net/nqe/pref_names.cc",                                                  # 1
    "services/preferences/public/cpp/tracked/pref_names.cc",                  # 3
)

# The `*_prefs.{h,cc}` convention: 469 more keys at M151, 456 KB.
PREFS_FILES = (
    "chrome/browser/accessibility/animation_policy_prefs.cc",                 # 3
    "chrome/browser/actor/ui/actor_ui_state_manager_prefs.h",                 # 1
    "chrome/browser/apps/intent_helper/intent_chip_display_prefs.cc",         # 1
    "chrome/browser/browser_switcher/browser_switcher_prefs.cc",              # 18
    "chrome/browser/content_settings/generated_cookie_prefs.cc",              # 2
    "chrome/browser/enterprise/reporting/prefs.cc",                           # 3
    "chrome/browser/enterprise/signin/enterprise_signin_prefs.h",             # 6
    "chrome/browser/glic/suggestions/contextual_cueing_prefs.h",              # 1
    "chrome/browser/indigo/indigo_prefs.h",                                   # 2
    "chrome/browser/login_detection/login_detection_prefs.cc",                # 1
    "chrome/browser/nearby_sharing/common/nearby_share_prefs.cc",             # 28
    "chrome/browser/platform_experience/prefs.h",                             # 4
    "chrome/browser/prefs/browser_prefs.cc",                                  # 155
    "chrome/browser/push_notification/prefs/push_notification_prefs.cc",      # 2
    "chrome/browser/tips/core/tips_prefs.cc",                                 # 9
    "chrome/browser/ui/read_anything/read_anything_prefs.h",                  # 18
    "chrome/browser/ui/safety_hub/safety_hub_prefs.h",                        # 21
    "chrome/browser/ui/side_search/side_search_prefs.cc",                     # 1
    "chrome/browser/ui/webui/bookmarks/bookmark_prefs.cc",                    # 2
    "chrome/browser/ui/webui/tab_search/tab_search_prefs.cc",                 # 2
    "chrome/browser/ui/zoom/chrome_zoom_level_prefs.cc",                      # 2
    "chrome/browser/webnn/webnn_prefs.h",                                     # 3
    "chrome/updater/prefs.cc",                                                # 5
    "components/contextual_tasks/public/prefs.cc",                            # 6
    "components/domain_reliability/domain_reliability_prefs.cc",              # 1
    "components/enterprise/browser/groups/groups_prefs.h",                    # 2
    "components/enterprise/client_certificates/core/prefs.cc",                # 2
    "components/enterprise/connectors/core/connectors_prefs.cc",              # 18
    "components/enterprise/connectors/core/connectors_prefs.h",               # 8
    "components/enterprise/data_controls/core/browser/prefs.h",               # 2
    "components/enterprise/device_trust/prefs.cc",                            # 2
    "components/enterprise/isolated_mode/prefs.cc",                           # 1
    "components/enterprise/network_header_injection/core/network_header_injection_prefs.h",# 1
    "components/guest_os/guest_os_prefs.cc",                                  # 5
    "components/headless/policy/headless_mode_prefs.cc",                      # 1
    "components/metrics/structured/structured_metrics_prefs.cc",              # 2
    "components/multistep_filter/core/prefs/multistep_filter_retention_prefs.h",# 3
    "components/omnibox/browser/omnibox_prefs.h",                             # 2
    "components/optimization_guide/core/model_execution/model_execution_prefs.cc",# 12
    "components/payments/core/payment_prefs.h",                               # 2
    "components/performance_manager/public/user_tuning/prefs.h",              # 15
    "components/proxy_config/proxy_prefs.cc",                                 # 5
    "components/regional_capabilities/regional_capabilities_prefs.h",         # 2
    "components/safe_browsing/content/common/file_type_policies_prefs.cc",    # 1
    "components/signin/public/base/signin_prefs.cc",                          # 23
    "components/skills/public/skills_prefs.cc",                               # 1
    "components/sync/service/sync_prefs.cc",                                  # 4
    "components/sync_sessions/session_sync_prefs.cc",                         # 1
    "components/translate/core/browser/translate_prefs.h",                    # 8
    "components/variations/service/google_groups_manager_prefs.h",            # 3
    "components/wallet/core/common/wallet_prefs.h",                           # 1
    "extensions/browser/blocklist_extension_prefs.cc",                        # 4
    "extensions/browser/extension_prefs.cc",                                  # 40
    "ui/accessibility/accessibility_prefs.cc",                                # 1
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
        FetchTarget("chrome/common/pref_names.h", "file",
                    note="pref keys (683 at M151)"),
        *(FetchTarget(path, "file", note="pref keys") for path in PREF_FILES),
        *(FetchTarget(path, "file", note="pref keys") for path in PREFS_FILES),

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
