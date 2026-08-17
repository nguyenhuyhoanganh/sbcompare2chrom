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
  preference behind it. That is the strongest join key between a vendor's UI
  and the browser core, and it survives the vendor replacing the UI entirely.

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
from ._cpp import line_of

RESOURCES_DIR = "chrome/browser/resources/"

# Interactive controls and structural markers, not layout wrappers.
CONTROL_TAGS = (
    "settings-toggle-button", "settings-dropdown-menu", "settings-radio-group",
    "settings-slider", "settings-checkbox", "settings-textarea",
    "settings-subpage", "settings-section",
    "controlled-button", "controlled-radio-button",
    "cr-toggle", "cr-checkbox", "cr-radio-group", "cr-radio-button",
    "cr-input", "cr-link-row", "cr-expand-button", "cr-button",
    "cr-searchable-drop-down", "cr-slider", "cr-textarea",
    "history-toolbar", "downloads-item", "bookmarks-item",
    "extensions-toggle-row", "extensions-item",
)

_TAG_RE = re.compile(
    r"<(" + "|".join(re.escape(t) for t in CONTROL_TAGS) + r")(?=[\s/>])([^>]*)>",
    re.S)
# Attribute names carry a Lit sigil: ?bool, .property, @event, or none.
_ATTR_RE = re.compile(r"[?.@]?([\w-]+)\s*=\s*\"([^\"]*)\"")
# Polymer  pref="{{prefs.a.b}}"  or  pref="[[prefs.a.b]]"
# Lit      .pref="${this.prefs.a.b}"
_PREF_RE = re.compile(
    r"[\{\[]{2}\s*(?:prefs\.)?([\w.]+?)(?:\.value)?\s*[\}\]]{2}"
    r"|\$\{\s*(?:this\.)?(?:prefs\.)?([\w.]+?)(?:\.value)?\s*\}")
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
    """
    if not rel_path.endswith(".html.ts"):
        return text
    m = _LIT_START_RE.search(text)
    if not m:
        return ""
    end = text.rfind("`")
    return text[m.end():end] if end > m.end() else text[m.end():]


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

        pref = ""
        pref_match = _PREF_RE.search(attrs.get("pref", ""))
        if pref_match:
            pref = pref_match.group(1) or pref_match.group(2) or ""

        label = ""
        for key in ("label", "page-title", "sub-label", "aria-label"):
            i18n = _I18N_RE.search(attrs.get(key, ""))
            if i18n:
                label = i18n.group(1)
                break

        # Identity, most stable first: the pref it drives, then its id, then
        # its label. Position is the last resort and the least stable.
        if pref:
            ident = f"pref:{pref}"
        elif attrs.get("id"):
            ident = f"id:{attrs['id']}"
        elif label:
            ident = f"label:{label}"
        else:
            n = seen.get(tag, 0)
            seen[tag] = n + 1
            ident = f"{tag}#{n}"

        facts.append(Fact(
            kind=KIND_WEBUI_CONTROL,
            key=f"{surface}/{page}/{ident}",
            name=ident,
            path=rel_path,
            line=line_of(masked, m.start()),
            attrs={
                "surface": surface,
                "page": page,
                "control": tag,          # the "dropdown became a toggle" signal
                "pref": pref,
                "label": label,
                "element_id": attrs.get("id", ""),
                "build_conditions": [expr for start, end, expr in spans
                                     if start <= m.start() < end],
            },
        ))
    return facts
