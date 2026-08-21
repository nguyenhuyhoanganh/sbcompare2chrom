"""Extract individual controls from desktop WebUI page templates.

Every ``chrome://`` page under ``chrome/browser/resources/`` declares its
controls in an HTML template. The control's *type is the element name*, which
is what makes "a dropdown became a toggle" mechanically detectable::

    <settings-toggle-button
        pref="{{prefs.download.prompt_for_download}}"
        label="$i18n{promptForDownload}">

    <controlled-button id="changeDownloadsPath"
        pref="[[prefs.download.default_directory]]"
        label="$i18n{changeDownloadLocation}">

Two attributes carry most of the value:

* the tag name -- ``settings-toggle-button``, ``settings-dropdown-menu``,
  ``cr-radio-group`` -- so a changed control type is a one-line diff;
* ``pref="{{prefs.x.y}}"`` -- a declarative link from this control to the
  preference behind it. That is the strongest join key between the UI and the
  browser core, and it survives the page being redesigned around it.

Templates also carry build-time platform conditionals (``<if expr="not
is_chromeos">``), the template-side equivalent of ``#if BUILDFLAG``. They are
recorded so a control that never compiles on our platform can be scored down
rather than read as a change.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List

from ..model import KIND_WEBUI_CONTROL, Fact
from ._cpp import PLATFORM, grit_platform_state, line_of

RESOURCES_DIR = "chrome/browser/resources/"

# What counts as a control, as a rule rather than a list of names.
#
# This used to be 27 tag names someone typed out, and it decayed the way every
# curated list in this project has decayed -- silently, because a tag nobody
# listed is a control nobody sees. Measured at M151 across the eight surfaces
# the default target set reads: 471 distinct custom elements appear in the
# templates, 2,462 times, and the list matched 902 of those occurrences (36%).
#
# The misses were not exotic. 41 of them bind a real preference, which makes
# them controls by definition: `settings-collapse-radio-button` alone writes one
# 27 times, and `wording.py` already carried a word for that very tag -- so the
# renderer knew about a control the extractor never emitted. `cr-icon-button`
# appears 143 times, 105 of them with an element id.
#
# So the question is answered by shape, the same move `targets.py` made when its
# file list decayed:
#
#   1. it binds a preference -- whatever it is called, something that writes a
#      user setting is a control;
#   2. a hyphen-separated segment of its tag names an interactive component
#      *and* it carries a stable identity, an element id or a label; or
#   3. it is one of the structural units a page is built from.
#
# Segments rather than substrings is what separates the button from the icon:
# `cr-icon-button` has a `button` segment, `cr-icon` has none.
#
# The identity requirement in rule 2 is what keeps widening from costing
# anything. An element with no pref, no id and no label can only be identified
# by its position -- "the third button in this file" -- which churns whenever
# the template is reordered. Measured at M151 the rule is strictly better than
# the list it replaces on every axis: 971 controls against 884, 190 of them
# binding a preference against 156, and positional identities down from 130
# (14%) to 15 (1%).
INTERACTIVE_SEGMENTS = frozenset((
    "button", "toggle", "checkbox", "radio", "group", "input", "select",
    "dropdown", "drop", "slider", "menu", "switch", "textarea", "combobox",
    "picker", "row", "searchable",
))

# Not interactive, but the units a page is made of: a page losing one is a
# change worth reporting, and no word in the tag says so.
STRUCTURAL_TAGS = frozenset((
    "settings-subpage", "settings-section",
    "history-toolbar", "downloads-item", "bookmarks-item", "extensions-item",
))

# Every custom element -- a tag with a hyphen. Which of them is a control is
# decided by `is_control` below, once the attributes are in hand, because rule 1
# cannot be answered from the tag name alone.
_TAG_RE = re.compile(r"<([a-z][a-z0-9]*(?:-[a-z0-9]+)+)(?=[\s/>])([^>]*)>", re.S)


def is_control(tag: str, pref: str, element_id: str = "", label: str = "") -> bool:
    """Whether this custom element is a control, by the rule above."""
    if pref or tag in STRUCTURAL_TAGS:
        return True
    if not (element_id or label):
        return False
    return any(seg in INTERACTIVE_SEGMENTS for seg in tag.split("-"))


# Attribute names carry a Lit sigil: ?bool, .property, @event, or none.
_ATTR_RE = re.compile(r"[?.@]?([\w-]+)\s*=\s*\"([^\"]*)\"")
# Polymer  pref="{{prefs.a.b}}"  or  pref="[[prefs.a.b]]"
# Lit      .pref="${this.prefs.a.b}"
#
# The `prefs.` prefix is required, not optional. Without it the pattern also
# matches a binding to an ordinary component property -- `${this.optedIn_}`,
# `[[fakePref_]]` -- and records it as though it were a preference key. At M151
# that was 27 of 156 bindings, none of which named a real pref, and each one
# both invented a dangling reference and gave the control an identity built on
# a private JavaScript member.
_PREF_RE = re.compile(
    r"[\{\[]{2}\s*prefs\.([\w.]+?)(?:\.value)?\s*[\}\]]{2}"
    r"|\$\{\s*(?:this\.)?prefs\.([\w.]+?)(?:\.value)?\s*\}")
_I18N_RE = re.compile(r"\$i18n(?:Polymer|Raw)?\{(\w+)\}")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_IF_RE = re.compile(r"<if\s+expr=\"([^\"]*)\"\s*>|</if>")

# Lit keeps the template inside a tagged literal in TypeScript:
#     export function getHtml(this: DownloadsItemElement) {
#       return html`<div id="date">...</div>`;
#     }
_LIT_START_RE = re.compile(r"\bhtml`")


def applies_to(path: str) -> bool:
    """Both template dialects.

    Chromium is migrating WebUI from Polymer (.html) to Lit (.html.ts), and
    the migration is far from uniform: measured at M151, settings is still
    243 .html to 6 Lit, while extensions is 2 to 33 and print_preview 2 to 32.
    Reading only .html leaves 23% of templates unread overall and nearly all
    of extensions, print_preview, history, bookmarks and downloads.
    """
    return path.startswith(RESOURCES_DIR) and (
        path.endswith(".html") or path.endswith(".html.ts"))


def template_body(text: str, rel_path: str) -> str:
    """The markup, whichever dialect wraps it.

    For Lit, take everything from the first ``html\\``` to the last backtick;
    the surrounding TypeScript declares no controls, and interpolated
    expressions inside are left in place for the attribute parser to skip.

    The leading TypeScript is blanked rather than cut, so offsets into the
    result still map onto the original file and reported line numbers point at
    the real line. Slicing it away made every Lit control's line number an
    offset into the template instead -- silently, since nothing checks a line
    number until someone opens the file and finds the wrong thing there.
    """
    if not rel_path.endswith(".html.ts"):
        return text
    m = _LIT_START_RE.search(text)
    if not m:
        return ""
    end = text.rfind("`")
    end = end if end > m.end() else len(text)
    head = "".join(c if c == "\n" else " " for c in text[:m.end()])
    return head + text[m.end():end]


def surface_of(rel_path: str) -> str:
    """chrome/browser/resources/downloads/foo.html -> downloads"""
    rest = rel_path[len(RESOURCES_DIR):] if rel_path.startswith(RESOURCES_DIR) else rel_path
    parts = rest.split("/")
    return parts[0] if parts else ""


def page_of(rel_path: str) -> str:
    """The page within a surface: settings/downloads_page/x.html -> downloads_page"""
    rest = rel_path[len(RESOURCES_DIR):] if rel_path.startswith(RESOURCES_DIR) else rel_path
    parts = rest.split("/")
    if len(parts) >= 3:
        return parts[1]
    name = parts[-1]
    for suffix in (".html.ts", ".html"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def _stem_of(rel_path: str) -> str:
    """downloads_page.html and downloads_page.html.ts are both downloads_page."""
    name = rel_path.rsplit("/", 1)[-1]
    for suffix in (".html.ts", ".html"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name.rsplit(".", 1)[0]


def _mask_html_comments(text: str) -> str:
    return _HTML_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), text)


def _condition_spans(text: str) -> List[tuple]:
    """(start, end, expr) for each <if expr="..."> ... </if> block."""
    spans: List[tuple] = []
    stack: List[tuple] = []
    for m in _IF_RE.finditer(text):
        if m.group(0).startswith("</"):
            if stack:
                start, expr = stack.pop()
                spans.append((start, m.start(), expr))
        else:
            stack.append((m.end(), m.group(1)))
    return spans


def extract(text: str, rel_path: str) -> List[Fact]:
    masked = _mask_html_comments(template_body(text, rel_path))
    surface = surface_of(rel_path)
    page = page_of(rel_path)
    spans = _condition_spans(masked)

    facts: List[Fact] = []
    seen: Dict[str, int] = {}
    for m in _TAG_RE.finditer(masked):
        tag, raw_attrs = m.group(1), m.group(2)
        attrs = dict(_ATTR_RE.findall(raw_attrs))

        # Two spellings, one link. Chromium began replacing the two-way
        # binding `pref="{{prefs.a.b}}"` with a plain attribute
        # `pref-key="a.b"`; at M151 twenty controls had moved and 125 had not.
        # Reading only the binding form makes a migrated control look like one
        # that stopped writing a preference at all -- the settings captions
        # page produced exactly that, four controls reported as repointed to
        # nothing when the key never changed.
        pref = attrs.get("pref-key", "").strip()
        if not pref:
            pref_match = _PREF_RE.search(attrs.get("pref", ""))
            if pref_match:
                pref = pref_match.group(1) or pref_match.group(2) or ""

        label = ""
        for key in ("label", "page-title", "sub-label", "aria-label"):
            i18n = _I18N_RE.search(attrs.get(key, ""))
            if i18n:
                label = i18n.group(1)
                break

        # Asked once the pref and the identity are in hand, because both are
        # part of the answer: binding a preference makes an element a control
        # whatever it is called, and an interactive tag with nothing to identify
        # it is not worth a fact.
        if not is_control(tag, pref, attrs.get("id", ""), label):
            continue

        conditions = [expr for start, end, expr in spans
                      if start <= m.start() < end]
        state = grit_platform_state(conditions)

        # Identity, most stable first: the pref it drives, then its id, then
        # its label. Position is the last resort and the least stable.
        #
        # The pref alone is not unique. A radio group and each of its buttons
        # bind the same pref, and Chromium routinely binds one pref from two
        # pages in the same directory. Measured at M148 across all eight
        # surfaces: 92 keys collided, swallowing 142 of 881 controls (16%), and
        # 15 of those collisions held more than one control *type* -- so which
        # one survived depended on filesystem walk order, and a control type
        # change could be reported that never happened. Qualifying by element
        # id resolves 61 of the 92 at a measured cost of 3 phantom add/remove
        # pairs in 481 controls (0.6%), because ids barely churn.
        if pref and attrs.get("id"):
            ident = f"pref:{pref}#{attrs['id']}"
        elif pref:
            ident = f"pref:{pref}"
        elif attrs.get("id"):
            ident = f"id:{attrs['id']}"
        elif label:
            ident = f"label:{label}"
        else:
            n = seen.get(tag, 0)
            seen[tag] = n + 1
            ident = f"{tag}#{n}"

        # ...and by the declaring file as well as the directory. `page` is the
        # directory, so two dialogs in one folder collided:
        # `settings/autofill_page/id:nicknameInput` is declared by both
        # credit_card_edit_dialog and iban_edit_dialog. 98 of 1,256 keys at
        # M151 collided that way, swallowing 198 controls. The file stem drops
        # both extensions, so a Polymer `.html` becoming a Lit `.html.ts` is
        # the same page and does not churn.
        facts.append(Fact(
            kind=KIND_WEBUI_CONTROL,
            key=f"{surface}/{page}/{_stem_of(rel_path)}/{ident}",
            name=ident,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={
                "surface": surface,
                "page": page,
                "file": _stem_of(rel_path),
                "control": tag,          # the "dropdown became a toggle" signal
                "pref": pref,
                "label": label,
                "element_id": attrs.get("id", ""),
                "build_conditions": conditions,
                # Resolved for the platform we ship, so a control GRIT excludes
                # from a Windows build can be scored down like a C++
                # declaration behind `#if BUILDFLAG(IS_CHROMEOS)` already was.
                # At M151, 14 of 1,256 controls are in that position.
                **({"platform_state": {PLATFORM: state}}
                   if state and state != "compiled" else {}),
            },
        ))
    return facts
