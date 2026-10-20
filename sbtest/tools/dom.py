"""Dump a page's DOM *through all shadow roots* with ready-to-use locators.

    python -m sbtest.tools.dom bookmarks                     # internal page by name
    python -m sbtest.tools.dom chrome://settings/downloads --interactive
    python -m sbtest.tools.dom /form.html --out artifacts/form_dom.txt
    python -m sbtest.tools.dom history --exec "web.type('history-app >>> #toolbar >>> cr-toolbar >>> cr-toolbar-search-field >>> input', 'abc')"
    python -m sbtest.tools.dom bookmarks --seed-bookmarks test_data/bookmarks.yaml:seed_basic
    python -m sbtest.tools.dom extensions --extension test_data/extensions/sample_addon

Each line: ``<indent>tag#id.class [role] aria="..." "text"  =>  locator``.
The locator after ``=>`` can be pasted into ``web.click(...)`` / page objects.
``--exec`` runs Python (names: web, session, site, Keys) before dumping; repeatable.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sbtest.tools.common import base_parser, resolve_url, start

JS_DUMP = r"""
const interactiveOnly = arguments[0], maxText = arguments[1], maxNodes = arguments[2];
const SKIP = new Set(['SCRIPT','STYLE','TEMPLATE','NOSCRIPT','LINK','META','SVG','PATH','IRON-ICON','CR-ICON']);
const INTERACTIVE = new Set(['A','BUTTON','INPUT','SELECT','TEXTAREA','CR-BUTTON','CR-ICON-BUTTON','CR-CHECKBOX',
  'CR-TOGGLE','CR-INPUT','CR-RADIO-BUTTON','CR-LINK-ROW','CR-MENU-SELECTOR','CR-EXPAND-BUTTON','CONTROLLED-BUTTON',
  'SETTINGS-TOGGLE-BUTTON','CR-TAB','CR-SEARCH-FIELD','CR-TOOLBAR-SEARCH-FIELD','MD-SELECT','SETTINGS-DROPDOWN-MENU']);
const visible = el => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
const cssEsc = s => CSS.escape(s);
// selector of el unique within its root (document or a shadowRoot)
const localSel = (el) => {
  const root = el.getRootNode();
  if (el.id && root.querySelectorAll('#' + cssEsc(el.id)).length === 1) return '#' + cssEsc(el.id);
  const parts = [];
  let cur = el;
  while (cur && cur.nodeType === 1) {
    let part = cur.tagName.toLowerCase();
    if (cur.id && root.querySelectorAll('#' + cssEsc(cur.id)).length === 1) { parts.unshift('#' + cssEsc(cur.id)); break; }
    const cls = Array.from(cur.classList).filter(c => !/^(iron-|style-scope|x-scope|selected|focused)/.test(c)).slice(0, 2);
    if (cls.length) part += '.' + cls.map(cssEsc).join('.');
    const parent = cur.parentElement || null;
    const sibs = parent ? Array.from(parent.children).filter(c => c.tagName === cur.tagName) :
                          Array.from((cur.parentNode || root).children || []).filter(c => c.tagName === cur.tagName);
    if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(cur) + 1})`;
    parts.unshift(part);
    if (root.querySelectorAll(parts.join(' > ')).length === 1) break;
    cur = parent;
    if (!cur) break;
  }
  return parts.join(' > ');
};
const deepSel = (el) => {
  const segs = [];
  let cur = el;
  while (cur) {
    segs.unshift(localSel(cur));
    const root = cur.getRootNode();
    cur = root instanceof ShadowRoot ? root.host : null;
  }
  return segs.join(' >>> ');
};
const ownText = el => Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.nodeValue).join(' ').replace(/\s+/g, ' ').trim();
const out = []; let count = 0;
const walk = (node, depth, inShadow) => {
  if (count > maxNodes) return;
  const kids = node.shadowRoot ? [...node.shadowRoot.children, ...node.children] : [...node.children];
  for (const el of kids) {
    if (SKIP.has(el.tagName)) continue;
    if (!visible(el) && el.tagName !== 'SLOT' && !el.shadowRoot) continue;
    const isInter = INTERACTIVE.has(el.tagName) || ['button','link','checkbox','menuitem','tab','switch','option','textbox','listitem','row','radio'].includes(el.getAttribute('role'));
    const txt = (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') ? (el.value || '') : ownText(el);
    if (!interactiveOnly || isInter) {
      count++;
      let line = '  '.repeat(depth) + el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
        + (el.classList.length ? '.' + Array.from(el.classList).slice(0, 3).join('.') : '');
      if (el.shadowRoot) line += ' [shadow]';
      const role = el.getAttribute('role'); if (role) line += ` [role=${role}]`;
      for (const a of ['aria-label', 'title', 'placeholder', 'type', 'name', 'href']) {
        const v = el.getAttribute(a); if (v) line += ` ${a}="${v.slice(0, 60)}"`;
      }
      if (el.hasAttribute('checked') || el.getAttribute('aria-checked') === 'true' || el.getAttribute('aria-pressed') === 'true') line += ' (checked)';
      if (el.hasAttribute('disabled')) line += ' (disabled)';
      if (txt) line += ` "${txt.slice(0, maxText)}"`;
      line += '  =>  ' + deepSel(el);
      out.push(line);
    }
    walk(el, interactiveOnly ? depth : depth + 1);
  }
};
walk(document.documentElement, 0);
if (count > maxNodes) out.push(`... truncated at ${maxNodes} nodes (use --interactive or --max-nodes)`);
return out.join('\n');
"""


def dump_dom(web, interactive: bool = False, max_text: int = 60, max_nodes: int = 4000) -> str:
    return web.driver.execute_script(JS_DUMP, interactive, max_text, max_nodes)


def main(argv=None) -> int:
    p = base_parser(__doc__.split("\n")[0])
    p.add_argument("url", help="internal page name (bookmarks, history...), /local-site-path or full URL")
    p.add_argument("--interactive", action="store_true", help="only clickable/typeable elements")
    p.add_argument("--exec", action="append", default=[], help="python to run before dumping (repeatable)")
    p.add_argument("--wait", type=float, default=1.0, help="seconds to let the page render")
    p.add_argument("--max-nodes", type=int, default=4000)
    p.add_argument("--out", help="write the dump to a file instead of stdout")
    p.add_argument("--screenshot", help="also save a screenshot to this path")
    p.add_argument("--uia", help="(Windows) also dump the native UIA tree to this path")
    p.add_argument("--seed-bookmarks", help="file.yaml:key - seed Bookmarks from test data before start")
    p.add_argument("--extension", action="append", default=[], help="unpacked extension dir to load (repeatable)")
    args = p.parse_args(argv)

    import time

    from selenium.webdriver.common.keys import Keys

    session, site = None, None
    try:
        session, site = start(args, "dom", extensions=args.extension, bookmarks_spec=args.seed_bookmarks)
        web = session.web
        web.open(resolve_url(session.cfg, site, args.url))
        time.sleep(args.wait)
        scope = {"web": web, "session": session, "site": site, "Keys": Keys, "native": session.native}
        for code in args.exec:
            exec(code, scope)  # noqa: S102 - developer tool
            time.sleep(args.wait)
        text = f"# URL: {web.url}\n# TITLE: {web.title}\n" + dump_dom(web, args.interactive, max_nodes=args.max_nodes)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"DOM dump written to {args.out}")
        else:
            sys.stdout.write(text + "\n")
        if args.screenshot:
            web.screenshot(args.screenshot)
        if args.uia and session.native:
            session.native.dump(args.uia)
    finally:
        if session:
            session.stop()
        if site:
            site.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
