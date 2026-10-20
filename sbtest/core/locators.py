"""One locator syntax for everything, including Shadow DOM (all chrome:// pages use it).

A locator is a string with an optional prefix, or a Selenium ``(By, value)`` tuple:

    "#id .class"                      CSS (default)
    "css=button.primary"              CSS
    "xpath=//div[@id='x']"            XPath (also any string starting with "/" or "(")
    "id=search"  "name=q"             by id / name attribute
    "bookmarks-app >>> #searchInput"  shadow path: each ">>>" steps into the shadowRoot
                                      of the element matched so far ("deep=" prefix optional)
    "deepcss=cr-toast"                CSS searched inside *every* shadow root (slower, handy)
    "text=Delete"                     element whose visible (composed) text is exactly "Delete"
    "text~=Deleted"                   element whose text contains "Deleted" (case-insensitive)
    "aria=Search bookmarks"           element whose aria-label / title / placeholder equals it

``text=``, ``text~=`` and ``aria=`` also pierce shadow roots and return the *deepest*
matching elements. Every API that takes a locator also accepts a WebElement.
"""
from __future__ import annotations

from dataclasses import dataclass

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

# ---------------------------------------------------------------- shadow-aware JS
_JS_COMMON = r"""
const scopeOf = (n) => (n && n.shadowRoot) ? n.shadowRoot : n;
const SKIP = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT']);
const visible = (el) => {
  if (!(el instanceof Element)) return false;
  const st = getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none') return false;
  return el.getClientRects().length > 0;
};
"""

JS_DEEP_PATH = _JS_COMMON + r"""
const segs = arguments[0], start = arguments[1];
let current = [start ? scopeOf(start) : document];
for (let i = 0; i < segs.length; i++) {
  const next = [];
  for (const r of current) {
    const scope = i === 0 ? r : scopeOf(r);
    if (!scope || !scope.querySelectorAll) continue;
    for (const el of scope.querySelectorAll(segs[i])) if (!next.includes(el)) next.push(el);
  }
  current = next;
  if (!current.length) break;
}
return current;
"""

JS_DEEP_CSS = _JS_COMMON + r"""
const sel = arguments[0], start = arguments[1];
const out = [];
const walk = (root) => {
  if (!root || !root.querySelectorAll) return;
  for (const el of root.querySelectorAll(sel)) out.push(el);
  for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot);
};
walk(start ? scopeOf(start) : document);
if (start && start.shadowRoot) {   // also the light DOM of the start element
  for (const el of start.querySelectorAll(sel)) if (!out.includes(el)) out.push(el);
}
return out;
"""

# Single pass over the *composed* tree (shadow roots + slotted nodes). Returns the
# deepest elements whose normalized text matches, so "text=Delete" yields the button,
# not every ancestor that contains it.
JS_DEEP_TEXT = _JS_COMMON + r"""
const target = arguments[0], mode = arguments[1], start = arguments[2];
const norm = (s) => s.replace(/\s+/g, ' ').trim();
const t = mode === 'contains' ? target.toLowerCase() : target;
const test = (s) => mode === 'contains' ? s.toLowerCase().includes(t) : s === t;
const out = [];
const kids = (n) => {
  if (n.shadowRoot) return Array.from(n.shadowRoot.childNodes);
  if (n.tagName === 'SLOT') {
    const a = n.assignedNodes({flatten: true});
    return a.length ? a : Array.from(n.childNodes);
  }
  return Array.from(n.childNodes);
};
const visit = (n) => {               // returns [text, matchedBelow]
  if (n.nodeType === 3) return [n.nodeValue, false];
  if (n.nodeType !== 1 && n.nodeType !== 11 && n.nodeType !== 9) return ['', false];
  if (n.nodeType === 1 && SKIP.has(n.tagName)) return ['', false];
  let text = '', below = false;
  for (const c of kids(n)) { const [ct, cb] = visit(c); text += ct; below = below || cb; }
  if (n.nodeType === 1) {
    const block = /^(DIV|P|LI|TR|TD|TH|BR|H[1-6]|SECTION|ARTICLE)$/.test(n.tagName);
    if (!below && test(norm(text)) && visible(n)) { out.push(n); below = true; }
    if (block) text = ' ' + text + ' ';
  }
  return [text, below];
};
visit(start ? start : document.documentElement);
return out;
"""

JS_DEEP_ARIA = _JS_COMMON + r"""
const target = arguments[0], start = arguments[1];
const out = [];
const walk = (root) => {
  for (const el of root.querySelectorAll('*')) {
    for (const a of ['aria-label', 'title', 'placeholder', 'label']) {
      if (el.getAttribute(a) === target) { out.push(el); break; }
    }
    if (el.shadowRoot) walk(el.shadowRoot);
  }
};
walk(start ? scopeOf(start) : document);
return out;
"""

JS_IS_VISIBLE = _JS_COMMON + "return visible(arguments[0]);"

# composed (shadow-including) visible text of an element or the whole page
JS_COMPOSED_TEXT = _JS_COMMON + r"""
const root = arguments[0] || document.body;
const kids = (n) => {
  if (n.shadowRoot) return Array.from(n.shadowRoot.childNodes);
  if (n.tagName === 'SLOT') { const a = n.assignedNodes({flatten: true}); return a.length ? a : Array.from(n.childNodes); }
  return Array.from(n.childNodes);
};
const parts = [];
const visit = (n) => {
  if (n.nodeType === 3) { parts.push(n.nodeValue); return; }
  if (n.nodeType === 1) {
    if (SKIP.has(n.tagName)) return;
    const st = getComputedStyle(n);
    if (st.display === 'none' || st.visibility === 'hidden') return;
    if (n.tagName === 'INPUT' || n.tagName === 'TEXTAREA') { parts.push(' ' + (n.value || '') + ' '); return; }
  }
  const block = n.nodeType === 1 && st_block(n);
  if (block) parts.push('\n');
  for (const c of kids(n)) visit(c);
  if (block) parts.push('\n');
};
const st_block = (el) => { const d = getComputedStyle(el).display; return d && !d.startsWith('inline'); };
visit(root);
return parts.join('').replace(/[ \t\r\f\v]+/g, ' ').replace(/ *\n */g, '\n').replace(/\n{2,}/g, '\n').trim();
"""


@dataclass(frozen=True)
class Locator:
    kind: str  # css | xpath | id | name | deep | deepcss | text | textc | aria
    value: str | tuple

    def __str__(self) -> str:
        return f"{self.kind}={self.value}"


def parse(spec) -> Locator:
    """Turn a locator string/tuple into a :class:`Locator`."""
    if isinstance(spec, Locator):
        return spec
    if isinstance(spec, tuple) and len(spec) == 2:
        by, value = spec
        mapping = {By.CSS_SELECTOR: "css", By.XPATH: "xpath", By.ID: "id", By.NAME: "name"}
        if by in mapping:
            return parse(f"{mapping[by]}={value}")
        return Locator("by", (by, value))
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError(f"Bad locator: {spec!r}")
    s = spec.strip()
    for prefix, kind in (("text~=", "textc"), ("text=", "text"), ("aria=", "aria"), ("deepcss=", "deepcss"),
                         ("deep=", "deep"), ("css=", "css"), ("xpath=", "xpath"), ("id=", "id"), ("name=", "name")):
        if s.startswith(prefix):
            value = s[len(prefix):]
            if kind == "css" and ">>>" in value:
                kind = "deep"
            if kind == "deep":
                return Locator("deep", tuple(p.strip() for p in value.split(">>>") if p.strip()))
            return Locator(kind, value)
    if s.startswith("/") or s.startswith("("):
        return Locator("xpath", s)
    if ">>>" in s:
        return Locator("deep", tuple(p.strip() for p in s.split(">>>") if p.strip()))
    return Locator("css", s)


def find_all(driver, spec, within: WebElement | None = None) -> list[WebElement]:
    """All elements matching ``spec`` (no waiting). ``within`` scopes the search."""
    if isinstance(spec, WebElement):
        return [spec]
    loc = parse(spec)
    ctx = within if within is not None else driver
    if loc.kind == "css":
        return ctx.find_elements(By.CSS_SELECTOR, loc.value)
    if loc.kind == "xpath":
        return ctx.find_elements(By.XPATH, loc.value)
    if loc.kind == "id":
        return ctx.find_elements(By.ID, loc.value)
    if loc.kind == "name":
        return ctx.find_elements(By.NAME, loc.value)
    if loc.kind == "by":
        return ctx.find_elements(*loc.value)
    if loc.kind == "deep":
        return driver.execute_script(JS_DEEP_PATH, list(loc.value), within) or []
    if loc.kind == "deepcss":
        return driver.execute_script(JS_DEEP_CSS, loc.value, within) or []
    if loc.kind in ("text", "textc"):
        mode = "contains" if loc.kind == "textc" else "exact"
        return driver.execute_script(JS_DEEP_TEXT, loc.value, mode, within) or []
    if loc.kind == "aria":
        return driver.execute_script(JS_DEEP_ARIA, loc.value, within) or []
    raise ValueError(f"Unknown locator kind: {loc.kind}")


def is_visible(driver, el: WebElement) -> bool:
    try:
        return bool(driver.execute_script(JS_IS_VISIBLE, el))
    except Exception:  # noqa: BLE001 - stale / detached counts as not visible
        return False
