/* Minimal DOM, enough to run the report's own script and observe what it does.
 *
 * The freeze this guards against is a runtime property -- how much DOM the page
 * builds per keystroke -- so asserting on the generated HTML text cannot see it.
 * Running the real script against a fake document can.
 *
 * Reads the script out of a generated report.html passed as argv[2] and prints
 * one JSON object of observations for the Python test to assert on.
 */
'use strict';
const fs = require('fs');

let detailRows = [];
class El {
  constructor(tag) {
    this.tag = tag; this._html = ''; this.dataset = {}; this.hidden = false;
    this.listeners = {}; this.value = ''; this.className = '';
    this.nextElementSibling = null; this.trCount = 0;
  }
  set innerHTML(v) { this._html = v; this.trCount = (v.match(/<tr/g) || []).length;
    this.paints = (this.paints || 0) + 1; }
  get innerHTML() {
    // esc() sets textContent then reads innerHTML back.
    if (this._html === '' && this._text !== undefined)
      return String(this._text).replace(/&/g, '&amp;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return this._html;
  }
  set textContent(v) { this._text = v; }
  get textContent() { return this._text === undefined ? '' : this._text; }
  addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
  querySelectorAll() { return []; }
  after(el) { detailRows.push(el); }
  remove() { this.removed = true; }
  get classList() { return { contains: c => this.className.split(' ').includes(c) }; }
}

const els = {};
for (const id of ['q', 'fb', 'fk', 'fg', 'fo', 'tb', 'cnt', 'more']) els[id] = new El(id);
global.document = {
  getElementById: id => els[id],
  querySelectorAll: () => [],
  createElement: t => new El(t),
};

// Rows are shaped like the real payload, which drops empty values -- so a row
// legitimately arrives without `we_patch`, `chromestatus` or `ours`. Every
// tenth one scores zero, because that is a real and reachable score (base 35
// for a removed pref, minus 45 for one not compiled on Windows, clamped) and
// the fixture used to give every row a truthy score. That is why nothing
// caught `score: 0` being dropped from the payload as if it were `false`,
// leaving 238 of 6,757 rows rendering the string `undefined` in the Score
// column of a real report.
const N = 3000;
global.window = { __FINDINGS__: Array.from({ length: N }, (_, i) => {
  const row = {
    name: 'Feature' + i, kind: 'base_feature',
    bucket: i < 40 ? 'breaking' : 'housekeeping', score: i % 10 === 0 ? 0 : 100 - (i % 100),
    change_type: 'modified', what: 'feature flag Feature' + i,
    why: 'flag_retired_on', where: 'content/public/common',
    signals: ['flag_retired_on'], paths: ['content/f' + i + '.cc'],
    areas: [], deltas: [['default_state', 'disabled', 'enabled']],
    reasons: ['base severity 75'], moved: 'disabled -> enabled',
    // The routing axis. A retired flag routes away from its own surface --
    // it is a config job, not a C++ one -- and every tenth row here is Mojo
    // so the filter has two values to tell apart.
    owner: i % 10 === 0 ? 'ipc' : 'config',
  };
  if (i < 40) { row.we_patch = ['content/f' + i + '.cc']; row.ours = true;
                row.chromestatus = 'x'.repeat(300); }
  return row;
}) };
global.window.__KINDS__ = { base_feature: 'Chromium feature flag' };
global.window.__BUCKETS__ = { breaking: 'Breaking', housekeeping: 'Housekeeping' };
global.window.__STORIES__ = { flag_retired_on: 'Shipped, then flag retired' };

let pending = null;
global.setTimeout = fn => { pending = fn; return 1; };
global.clearTimeout = () => { pending = null; };
const flush = () => { if (pending) { const f = pending; pending = null; f(); } };

const raw = fs.readFileSync(process.argv[2], 'utf8');
const js = raw.split('<script>').slice(1).map(s => s.split('</script>')[0]).pop();
eval(js);

const out = { total: N, initialRows: els.tb.trCount, initialCount: els.cnt.textContent,
              detailsBuiltUpfront: detailRows.length, moreShown: !els.more.hidden };

// Nothing may render as `undefined`. Every cell comes from a field the payload
// is allowed to omit, so a missing key has to print as empty, never as the
// word JavaScript uses for it.
out.undefinedInRows = /undefined/.test(els.tb.innerHTML);

// A zero score has to render as 0. Filtering to breaking puts all 40 of them
// on one page, four of which score zero. The script is eval'd, so its own
// functions are out of scope here -- everything goes through the DOM, as the
// listeners above do.
els.fb.value = 'breaking';
els.fb.listeners['change'].forEach(f => f());
out.zeroRendersAsZero = /class="score[^"]*">0</.test(els.tb.innerHTML);
out.undefinedAfterFilter = /undefined/.test(els.tb.innerHTML);
els.fb.value = '';
els.fb.listeners['change'].forEach(f => f());

// The owner filter narrows to exactly the rows carrying that owner. It is a
// fifth dropdown over the same `match`, so an unwired one would silently show
// everything rather than error.
els.fo.value = 'ipc';
els.fo.listeners['change'].forEach(f => f());
out.ownerFilterCount = els.cnt.textContent;
els.fo.value = '';
els.fo.listeners['change'].forEach(f => f());
out.allOwnersRestores = els.cnt.textContent;

// Type a word one character at a time; only the debounced tail should run.
// Counting DOM rebuilds is the measure that matters: the row count after
// filtering happens to be a full page either way, so it cannot tell a
// debounced input from one that repaints on every character.
els.tb.paints = 0;
for (const ch of 'Feature1') {
  els.q.value += ch;
  els.q.listeners['input'].forEach(f => f());
}
out.paintsWhileTyping = els.tb.paints;
flush();
out.afterDebounce = els.cnt.textContent;
out.rowsAfterFilter = els.tb.trCount;
out.paintsAfterDebounce = els.tb.paints;

// Expand one row: the detail markup must be built now, not earlier.
const row = new El('tr'); row.className = 'row'; row.dataset.i = '1';
els.tb.listeners['click'].forEach(f => f({ target: { closest: () => row } }));
out.detailsAfterClick = detailRows.length;
out.detailHasEvidence = detailRows.length > 0 &&
  detailRows[0].innerHTML.includes('flag_retired_on') &&
  detailRows[0].innerHTML.includes('base severity 75');

// Collapse.
row.nextElementSibling = detailRows[0];
els.tb.listeners['click'].forEach(f => f({ target: { closest: () => row } }));
out.detailRemovedOnSecondClick = detailRows[0].removed === true;

// Paging.
els.more.listeners['click'].forEach(f => f());
out.rowsAfterShowMore = els.tb.trCount;

console.log(JSON.stringify(out));
