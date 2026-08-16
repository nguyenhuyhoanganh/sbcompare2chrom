"""Extract Blink runtime-enabled features (the web-platform API surface).

``runtime_enabled_features.json5`` is the closest thing Chromium has to a
machine-readable "what web APIs are on, and where" manifest.  Each entry
carries a status of ``stable`` / ``experimental`` / ``test``, either globally
or per platform:

    { name: "ExampleFeature", status: {"Android": "stable", "Win": "experimental"} }

An ``experimental -> stable`` transition is a web API becoming visible to real
users.  For a downstream browser that is simultaneously a compatibility signal
(sites will start using it), a QA signal (it needs test coverage), and
occasionally a conflict signal (the vendor may already ship its own
implementation of the same API).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from .. import jsonc
from ..model import KIND_BLINK_RUNTIME, Fact

FILENAME = "runtime_enabled_features.json5"

# json5 status keys -> our normalized platform names.
_PLATFORM_KEYS = {
    "Android": "android",
    "Win": "windows",
    "Mac": "mac",
    "Linux": "linux",
    "ChromeOS": "chromeos",
    "iOS": "ios",
}

STATUS_ORDER = {"": 0, "test": 1, "experimental": 2, "stable": 3}


def applies_to(path: str) -> bool:
    return os.path.basename(path) == FILENAME


def _normalize_status(status: Any) -> Dict[str, str]:
    """Return {platform: status} plus a "default" entry when one is implied.

    Omitting "default" in the dict form means *not enabled* on unlisted
    platforms -- a subtlety documented in the json5 header that is easy to get
    backwards, so it is encoded here once.
    """
    out: Dict[str, str] = {}
    if isinstance(status, str):
        for norm in _PLATFORM_KEYS.values():
            out[norm] = status
        out["default"] = status
        return out
    if isinstance(status, dict):
        default = status.get("default", "")
        for norm in _PLATFORM_KEYS.values():
            out[norm] = default
        for key, value in status.items():
            if key == "default":
                continue
            norm = _PLATFORM_KEYS.get(key)
            if norm:
                out[norm] = value
        out["default"] = default
        return out
    return {}


def extract(text: str, rel_path: str) -> List[Fact]:
    try:
        doc = jsonc.loads(text)
    except jsonc.Json5Error:
        return []
    if not isinstance(doc, dict):
        return []
    data = doc.get("data") or []
    facts: List[Fact] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        status = entry.get("status", "")
        per_platform = _normalize_status(status)
        attrs: Dict[str, Any] = {
            "status": status if isinstance(status, str) else "per-platform",
            "platform_status": per_platform,
            "android_status": per_platform.get("android", ""),
        }
        # Carry through the fields that describe how the flag is wired up:
        # these are what break downstream overrides when they change.
        for field in ("base_feature", "base_feature_status", "public",
                      "origin_trial_feature_name", "depends_on", "implied_by",
                      "copied_from_base_feature_if", "settable_from_internals",
                      "origin_trial_allows_third_party", "browser_process_read_access",
                      "browser_process_read_write_access"):
            if field in entry:
                attrs[field] = entry[field]
        facts.append(Fact(
            kind=KIND_BLINK_RUNTIME,
            key=name,
            name=name,
            path=rel_path,
            attrs=attrs,
        ))
    return facts


def status_rank(status: str) -> int:
    return STATUS_ORDER.get(status or "", 0)
