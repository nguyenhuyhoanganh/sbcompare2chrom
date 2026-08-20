"""Say what a finding is, in words, and group findings by what happened.

A report is a list of identifiers, and an identifier is not a description.
`AAPMBlocksWebGPU`, `AriaAttributes.ariaVirtualContent` and
`blink.mojom.AIManager.CreateLanguageModel` are each perfectly precise and each
require the reader to already know which of thirteen things they are looking
at. The kind column names the category, but a category and a sentence are not
the same help: "Mojo method" does not say that a process call is involved, and
"Preference" does not say that the thing at risk is data already on a user's
disk.

For the `chrome://` surfaces the identifier was worse than unhelpful. `id:cancelButton` says nothing on its own: it does not say which
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

The same gap existed one level up. A report is 2,792 rows, and rows are not
what happened: 77 of them are one thing ("these flags are now ON by default on
Windows") and 40 are another ("these Mojo methods changed signature, which is an
ABI break"). The diff engine already writes those sentences -- they are the
signal labels -- and they were reachable only by expanding a single table row.
Grouping findings by the signal that set their severity turns the list into
about forty things that happened, ordered by how much they weigh.

This module is presentation only -- it invents no facts and drops none. Every
finding it shows is also in the table below it and in the JSON.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ..diff import SIGNAL_LABELS, leading_signal
from ..model import (
    ADDED,
    KIND_BASE_FEATURE,
    KIND_BLINK_RUNTIME,
    KIND_FEATURE_PARAM,
    KIND_FLAG_ENTRY,
    KIND_IDL_INTERFACE,
    KIND_IDL_MEMBER,
    KIND_MOJO_INTERFACE,
    KIND_MOJO_METHOD,
    KIND_PREF,
    KIND_SWITCH,
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

# What each kind *is*, in the fewest words that still say why it matters. The
# kind label names the category ("Mojo method"); this names the consequence
# ("process call"), which is the half a reader outside the project is missing.
KIND_WORDS = {
    KIND_BASE_FEATURE: "feature flag",
    KIND_FEATURE_PARAM: "flag setting",
    KIND_BLINK_RUNTIME: "web API flag",
    KIND_IDL_INTERFACE: "web API",
    KIND_IDL_MEMBER: "web API",
    KIND_MOJO_INTERFACE: "process interface",
    KIND_MOJO_METHOD: "process call",
    KIND_SWITCH: "command-line switch",
    KIND_PREF: "user setting",
    KIND_FLAG_ENTRY: "chrome://flags entry",
    KIND_WEBUI_ROUTE: "page",
    KIND_WEBUI_CONTROL: "control",
    KIND_WEBUI_GATE: "visibility switch",
}

# `enabled` and `disabled` are the source's words; on and off are the reader's.
# An empty status is Blink's way of saying a flag exists and is not on
# anywhere, which rendered as a bare arrow pointing at nothing.
STATE_WORDS = {"enabled": "on", "disabled": "off",
               "not_compiled": "not in our build", "conditional": "conditional",
               "": "not enabled", None: "not enabled"}


def state_word(value) -> str:
    return STATE_WORDS.get(value, str(value) if value else "not enabled")


def _platform_move(change, attr: str, platform: str = "windows") -> str:
    """"off → on for Windows", when the platform's own value moved."""
    delta = change.deltas.get(attr)
    if not (isinstance(delta, list) and len(delta) == 2):
        return ""
    old, new = delta
    if not (isinstance(old, dict) and isinstance(new, dict)):
        return ""
    a, b = old.get(platform), new.get(platform)
    if a == b:
        return ""
    return f"{state_word(a)} → {state_word(b)} for {platform.title()}"


def _plain_move(change, attr: str) -> str:
    delta = change.deltas.get(attr)
    if isinstance(delta, list) and len(delta) == 2 and delta[0] != delta[1]:
        return f"{state_word(delta[0])} → {state_word(delta[1])}"
    return ""


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

    word = KIND_WORDS.get(change.kind, "")
    name = change.name

    if change.kind == KIND_BASE_FEATURE:
        # The platform's own value, not the global one. They routinely
        # disagree, and the global one is not what our users get.
        moved = (_platform_move(change, "platform_state")
                 or _plain_move(change, "default_state"))
        state = (attrs.get("platform_state") or {}).get("windows") \
            if isinstance(attrs.get("platform_state"), dict) else None
        if moved:
            return f"{word} {name} — {moved}"
        if change.change_type == ADDED and state:
            return f"{word} {name} — arrives {state_word(state)} for Windows"
        return f"{word} {name}"

    if change.kind == KIND_FEATURE_PARAM:
        owner = attrs.get("feature")
        out = f"{word} {name}" + (f" of {owner}" if owner else "")
        moved = _plain_move(change, "default")
        return f"{out} — {moved}" if moved else out

    if change.kind == KIND_BLINK_RUNTIME:
        moved = (_platform_move(change, "platform_status")
                 or _plain_move(change, "status"))
        status = attrs.get("windows_status") or attrs.get("status")
        if moved:
            return f"{word} {name} — {moved}"
        if change.change_type == ADDED and status:
            return f"{word} {name} — arrives {state_word(status)}"
        return f"{word} {name}"

    if change.kind == KIND_IDL_INTERFACE:
        return f"{word} {attrs.get('idl_kind') or 'interface'} {name}"

    if change.kind == KIND_IDL_MEMBER:
        member = attrs.get("member_type") or "member"
        gate = attrs.get("runtime_enabled")
        out = f"{word} {member} {change.key}"
        return f"{out} (behind {gate})" if gate else out

    if change.kind == KIND_MOJO_INTERFACE:
        count = attrs.get("method_count")
        out = f"{word} {change.key}"
        return f"{out} ({count} calls)" if count else out

    if change.kind == KIND_MOJO_METHOD:
        return f"{word} {change.key}()"

    if change.kind == KIND_SWITCH:
        return f"{word} --{name}"

    if change.kind == KIND_PREF:
        # The key is the contract with data already on the user's disk, so it
        # is the thing to show; a renamed C++ constant is a build problem and
        # the signal already says so.
        return f"{word} {name}"

    if change.kind == KIND_FLAG_ENTRY:
        expiry = attrs.get("expiry_milestone")
        moved = _plain_move(change, "expiry_milestone")
        out = f"{word} #{name}"
        if moved:
            return f"{out} — removal {moved}"
        return f"{out} (removal M{expiry})" if expiry else out

    return name


def story_of(change) -> Tuple[str, str]:
    """(id, headline) -- the one sentence saying why this row is in the report.

    The signal labels are already written as that sentence ("Shipped, then flag
    retired -- behaviour is now permanent and can no longer be turned off"), and
    until now they were only reachable by expanding a table row. Grouping on
    them turns 2,792 rows into about forty things that happened.

    The pick has to be the signal that set the severity, or a finding would be
    filed under one story and ranked by another. When a change carries no signal
    at all -- a flag that simply arrived, with no default to move -- the
    direction and the kind are the whole story, so they are the headline.
    """
    top = leading_signal(change)
    if top:
        return top, SIGNAL_LABELS.get(top, top)
    word = KIND_WORDS.get(change.kind, change.kind.replace("_", " "))
    # The word leads only in the "New ..." form. `chrome://flags entry` is a
    # lowercase URL scheme, and any headline that starts with it and then
    # capitalises reads as `Chrome://flags entry`.
    lead = {ADDED: "New", REMOVED: "Removed", MODIFIED: "Changed"}
    return (f"{change.change_type}:{change.kind}",
            f"{lead.get(change.change_type, 'Changed')} {word}")


class Block:
    """A named pile of findings, and the counts a reader needs above it."""

    __slots__ = ("name", "title", "items")

    def __init__(self, name: str, title: str = ""):
        self.name = name
        self.title = title or name
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

    def severity(self) -> int:
        return max((f.change.severity for f in self.items), default=0)

    def sorted_items(self) -> List[Finding]:
        # Additions first: "what is new here" is the question people arrive
        # with. Within a direction, the highest score leads.
        order = {ADDED: 0, MODIFIED: 1, REMOVED: 2}
        return sorted(self.items,
                      key=lambda f: (order.get(f.change.change_type, 3),
                                     -f.score, f.change.key))


class Screen(Block):
    """One `chrome://` page, and everything that moved on it."""


class Story(Block):
    """One thing that happened, and every finding it happened to."""


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


def summarize(screens: Sequence[Block]) -> Dict[str, int]:
    return {
        "screens": len(screens),
        "added": sum(s.counts()[ADDED] for s in screens),
        "changed": sum(s.counts()[MODIFIED] for s in screens),
        "removed": sum(s.counts()[REMOVED] for s in screens),
    }


def build_stories(findings: Sequence[Finding],
                  kinds: Sequence[str]) -> List[Story]:
    """Group findings of these kinds by what happened to them.

    Heaviest first, because the order is the recommendation: a story whose
    signal carries severity 80 is read before one carrying 25, however many
    rows the smaller one has.
    """
    keep = set(kinds)
    stories: Dict[str, Story] = {}
    for finding in findings:
        if finding.change.kind not in keep:
            continue
        key, headline = story_of(finding.change)
        stories.setdefault(key, Story(key, headline)).items.append(finding)
    return sorted(stories.values(),
                  key=lambda s: (-s.severity(), -len(s.items), s.title))
