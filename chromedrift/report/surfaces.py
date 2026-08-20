"""Turn the WebUI findings into "what changed on each screen".

A report is a list of identifiers, and for the `chrome://` surfaces that is the
wrong shape. `id:cancelButton` says nothing on its own: it does not say which
page it is on, whether it arrived or vanished, or what kind of control it is --
and the same loadTimeData key appears nine times because nine different pages
set it. A reader scanning that list cannot answer the one question they came
with, which is "what is different about this screen".

The data to answer it was already on the facts and simply never rendered. Every
control carries its surface, its page, its file, its tag and the preference it
writes; every route carries its path and its guard; every gate carries the
handler that sets it. Grouping by (surface, page) and putting those fields into
words costs nothing at extraction time and turns a flat list into a set of small
per-screen diffs.

This module is presentation only -- it invents no facts and drops none. Every
finding it shows is also in the table below it and in the JSON.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..model import (
    ADDED,
    KIND_WEBUI_CONTROL,
    KIND_WEBUI_GATE,
    KIND_WEBUI_ROUTE,
    MODIFIED,
    REMOVED,
    Finding,
)

WEBUI_KINDS = (KIND_WEBUI_ROUTE, KIND_WEBUI_CONTROL, KIND_WEBUI_GATE)

# A tag name is the control's type -- that is what makes "a dropdown became a
# toggle" mechanically visible -- but `settings-dropdown-menu` is jargon in a
# summary meant to be skimmed.
CONTROL_WORDS = (
    ("toggle", "toggle"),
    ("dropdown", "dropdown"),
    ("radio-group", "radio group"),
    ("radio-button", "radio button"),
    ("checkbox", "checkbox"),
    ("slider", "slider"),
    ("link-row", "link row"),
    ("collapse-radio-button", "radio button"),
    ("button", "button"),
    ("input", "text field"),
    ("textarea", "text box"),
    ("section", "section"),
    ("subpage", "subpage"),
    ("card", "card"),
    ("list", "list"),
    ("menu", "menu"),
    ("dialog", "dialog"),
)

# What the reader should take from each direction, in the words of the surface
# rather than of the diff engine.
VERB = {ADDED: "new", REMOVED: "gone", MODIFIED: "changed"}
MARK = {ADDED: "+", REMOVED: "−", MODIFIED: "~"}


def control_word(tag: str) -> str:
    """`settings-dropdown-menu` -> `dropdown`, and unknown tags stay verbatim."""
    low = (tag or "").lower()
    for needle, word in CONTROL_WORDS:
        if needle in low:
            return word
    return tag or "control"


def _attrs(change) -> dict:
    return change.after or change.before or {}


def _both(change) -> List[dict]:
    return [a for a in (change.before, change.after) if a]


def screen_of(change) -> Optional[str]:
    """"settings › privacy_page", or None when this is not a screen at all.

    A gate lives in a C++ handler rather than under `resources/`, so its screen
    is named after the handler: `settings_ui.cc` sets keys for
    `chrome://settings`. Without that, every gate landed in one undifferentiated
    pile -- which is how `webuiRefresh2026` came to appear nine times with
    nothing to tell the nine apart.
    """
    if change.kind == KIND_WEBUI_CONTROL:
        for attrs in _both(change):
            surface, page = attrs.get("surface"), attrs.get("page")
            if surface:
                return f"{surface} › {page}" if page and page != surface else surface
        # Older snapshots kept the location only in the key.
        parts = change.key.split("/")
        if len(parts) >= 2:
            return f"{parts[0]} › {parts[1]}"
        return None
    if change.kind == KIND_WEBUI_ROUTE:
        for attrs in _both(change):
            if attrs.get("surface"):
                return str(attrs["surface"])
        return "settings"
    if change.kind == KIND_WEBUI_GATE:
        for attrs in _both(change):
            handler = attrs.get("handler")
            if handler:
                return _surface_from_handler(str(handler))
        return _surface_from_handler(change.key.split("/")[0])
    return None


def _surface_from_handler(handler: str) -> str:
    """`new_tab_page_ui` -> `new_tab_page`, `history_util` -> `history`."""
    for suffix in ("_ui", "_util", "_handler", "_manager",
                   "_localized_strings_provider"):
        if handler.endswith(suffix):
            return handler[: -len(suffix)] or handler
    return handler


def describe(change) -> str:
    """One line saying what this thing is, in words rather than identifiers."""
    attrs = _attrs(change)

    if change.kind == KIND_WEBUI_CONTROL:
        tag = str(attrs.get("control") or "")
        # A type change is the headline, so show both sides of it.
        moved = change.deltas.get("control")
        if isinstance(moved, list) and len(moved) == 2:
            word = f"{control_word(str(moved[0]))} → {control_word(str(moved[1]))}"
        else:
            word = control_word(tag)
        label = (attrs.get("label") or attrs.get("element_id")
                 or change.name.split(":")[-1])
        out = f"{word} — {label}" if label else word
        pref = attrs.get("pref")
        if pref:
            out += f" (writes {pref})"
        return out

    if change.kind == KIND_WEBUI_ROUTE:
        route = attrs.get("route") or change.name
        guards = attrs.get("guards") or []
        out = f"page {route}"
        if guards:
            out += f" (shown when {', '.join(str(g) for g in guards[:2])})"
        return out

    if change.kind == KIND_WEBUI_GATE:
        features = attrs.get("features") or []
        out = f"visibility switch {change.name}"
        if features:
            out += f" (from {', '.join(str(f) for f in features[:2])})"
        return out

    return change.name


class Screen:
    """One `chrome://` page, and everything that moved on it."""

    __slots__ = ("name", "items")

    def __init__(self, name: str):
        self.name = name
        self.items: List[Finding] = []

    def counts(self) -> Dict[str, int]:
        out = {ADDED: 0, REMOVED: 0, MODIFIED: 0}
        for finding in self.items:
            out[finding.change.change_type] = out.get(
                finding.change.change_type, 0) + 1
        return out

    def headline(self) -> str:
        counts = self.counts()
        parts = [f"{counts[k]} {VERB[k]}" for k in (ADDED, MODIFIED, REMOVED)
                 if counts.get(k)]
        return " · ".join(parts)

    def top_score(self) -> int:
        return max((f.score for f in self.items), default=0)

    def sorted_items(self) -> List[Finding]:
        # Additions first: "what is new here" is the question people arrive
        # with. Within a direction, the highest score leads.
        order = {ADDED: 0, MODIFIED: 1, REMOVED: 2}
        return sorted(self.items,
                      key=lambda f: (order.get(f.change.change_type, 3),
                                     -f.score, f.change.key))


def build(findings: Sequence[Finding]) -> List[Screen]:
    """Group every WebUI finding by the screen it belongs to.

    Ordered by how much moved, because a screen with one relabelled button is
    not the one to read first.
    """
    screens: Dict[str, Screen] = {}
    for finding in findings:
        if finding.change.kind not in WEBUI_KINDS:
            continue
        name = screen_of(finding.change)
        if not name:
            continue
        screens.setdefault(name, Screen(name)).items.append(finding)
    return sorted(screens.values(),
                  key=lambda s: (-len(s.items), -s.top_score(), s.name))


def summarize(screens: Sequence[Screen]) -> Dict[str, int]:
    return {
        "screens": len(screens),
        "added": sum(s.counts()[ADDED] for s in screens),
        "changed": sum(s.counts()[MODIFIED] for s in screens),
        "removed": sum(s.counts()[REMOVED] for s in screens),
    }
