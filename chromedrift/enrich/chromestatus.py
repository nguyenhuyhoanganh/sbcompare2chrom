"""Attach chromestatus.com context to findings.

The extractors say *what* changed; chromestatus says *why*, in prose a human
wrote: a summary, the spec link, the shipping milestone, and whether there is
a known interoperability story.

It matters because the tool stops at the evidence.  A row saying
``"CSSAnchorScope"`` went from experimental to stable invites whoever reads it
to guess what that means; the feature's own one-paragraph summary and spec URL
let them look it up instead.  Enrichment is best-effort and cached, so an
offline run simply produces findings without it.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List

from ..acquire import AcquireError, _http_get
from ..model import Finding

API = "https://chromestatus.com/api/v0"


def _strip_xssi(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    if text.startswith(")]}"):
        text = text.split("\n", 1)[1] if "\n" in text else "{}"
    return text


def fetch_milestone_features(milestone: int, cache_dir: str,
                             refresh: bool = False,
                             log=lambda m: None) -> List[dict]:
    """Every feature chromestatus records as landing in ``milestone``."""
    path = os.path.join(cache_dir, "chromestatus", f"m{milestone}.json")
    if os.path.exists(path) and not refresh:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass

    url = f"{API}/features?milestone={milestone}"
    try:
        raw = _http_get(url, timeout=90, retries=3)
    except AcquireError as exc:
        log(f"  chromestatus m{milestone} unavailable: {exc}")
        return []
    try:
        doc = json.loads(_strip_xssi(raw))
    except json.JSONDecodeError:
        return []

    features: List[dict] = []
    by_type = doc.get("features_by_type") or {}
    if isinstance(by_type, dict):
        for shipping_type, entries in by_type.items():
            for entry in entries or []:
                if isinstance(entry, dict):
                    entry = dict(entry)
                    entry["_shipping_type"] = shipping_type
                    features.append(entry)
    elif isinstance(doc.get("features"), list):
        features = [f for f in doc["features"] if isinstance(f, dict)]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(features, fh)
    log(f"  chromestatus m{milestone}: {len(features)} features")
    return features


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def build_index(features: List[dict]) -> Dict[str, dict]:
    """Index chromestatus entries by a normalized name for fuzzy joining."""
    index: Dict[str, dict] = {}
    for feature in features:
        keys = {feature.get("name", "")}
        for extra in ("feature_name", "shortname"):
            if feature.get(extra):
                keys.add(feature[extra])
        for key in keys:
            norm = _normalize(key)
            if norm and norm not in index:
                index[norm] = feature
    return index


def _compact(feature: dict) -> dict:
    """Keep only the fields a reader needs, in a shape a report can print.

    The summary is collapsed to a single line first. Chromestatus prose is
    written for a web page and routinely carries blank lines and indented code
    samples; 84 of 200 entries in a real M143 -> M151 window did. Printed raw
    into a markdown list they break out of it, so the fenced CSS in an entry
    about `@scroll-state` became top-level prose and the `Spec:` line after it
    re-entered at the wrong depth. Collapsing here rather than in the renderer
    also means the truncation below counts characters a reader will see, and
    that every consumer -- markdown, HTML, `report.json` -- gets the same text.
    """
    summary = re.sub(r"\s+", " ", (feature.get("summary") or "")).strip()
    if len(summary) > 600:
        summary = summary[:600].rsplit(" ", 1)[0] + "..."
    out = {
        "name": feature.get("name"),
        "summary": summary,
        "category": feature.get("category"),
        "shipping": feature.get("_shipping_type"),
        "id": feature.get("id"),
    }
    standards = feature.get("standards") or {}
    if isinstance(standards, dict) and standards.get("spec"):
        out["spec"] = standards["spec"]
    browsers = feature.get("browsers") or {}
    if isinstance(browsers, dict):
        chrome = browsers.get("chrome") or {}
        if chrome.get("desktop") or chrome.get("windows"):
            out["shipped_milestone"] = chrome.get("windows") or chrome.get("desktop")
        for other in ("ff", "safari"):
            view = (browsers.get(other) or {}).get("view") or {}
            if view.get("text"):
                out[f"{other}_position"] = view["text"]
    return {k: v for k, v in out.items() if v}


def milestone_brief(milestones: List[int], cache_dir: str,
                    refresh: bool = False, log=lambda m: None) -> List[dict]:
    """What Chromium says shipped across a milestone span, as shared context.

    Joining chromestatus to individual findings barely works: its names are
    human prose ("Allow more characters in javascript DOM APIs") while ours are
    identifiers, and fuzzy matching tops out around 2% before it starts
    inventing pairs.

    So the list is carried whole instead of matched: it says what Chromium
    intended to ship in this window without pretending to know which finding
    each entry belongs to.

    **Newest milestone first, and nothing is dropped here.** Both of those were
    wrong, and in the same direction. The list used to be filled oldest-first
    and cut at 200, so on a real 143 -> 151 run it held 200 entries covering
    M144 to M150 and *nothing at all from M151* -- the milestone actually being
    adopted, and the only one the reader is certain to care about. Nothing said
    so either: the renderer's "... and N more" line never fired, because the
    truncation had already happened here, and `report.json` genuinely did not
    hold the rest despite the report promising it did.

    Capping is the renderer's job, because the renderer is the only place that
    knows what it cut. Deduplication keeps the newest milestone a feature
    appears under, for the same reason the order does.
    """
    out: List[dict] = []
    seen = set()
    for milestone in sorted(milestones, reverse=True):
        for feature in fetch_milestone_features(milestone, cache_dir, refresh, log):
            name = feature.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            entry = _compact(feature)
            entry["milestone"] = milestone
            if entry.get("summary") and len(entry["summary"]) > 220:
                entry["summary"] = entry["summary"][:220].rsplit(" ", 1)[0] + "..."
            out.append(entry)
    return out


def enrich(findings: List[Finding], milestones: List[int], cache_dir: str,
           refresh: bool = False, log=lambda m: None) -> int:
    """Attach chromestatus context in place; returns how many were enriched."""
    index: Dict[str, dict] = {}
    for milestone in milestones:
        index.update(build_index(
            fetch_milestone_features(milestone, cache_dir, refresh, log)))
    if not index:
        return 0

    hits = 0
    for finding in findings:
        for candidate in (finding.change.name, finding.change.key):
            entry = index.get(_normalize(candidate))
            if entry:
                finding.enrichment["chromestatus"] = _compact(entry)
                hits += 1
                break
    log(f"  chromestatus matched {hits}/{len(findings)} findings")
    return hits
