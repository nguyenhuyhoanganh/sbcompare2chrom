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
for (const id of ['q', 'fb', 'fk', 'fg', 'fo', 'fp', 'tb', 'cnt', 'more'])
  els[id] = new El(id);
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
  // Provenance, in the three shapes the page must tell apart. 30 rows each,
  // so a filter that quietly lumps two of them together shows up as a count.
  // `touched` is the floor the enricher falls back to when nothing names the
  // fact: real CLs, and not an answer to "why did this change".
  const prov = i % 100;
  if (prov === 3 || prov === 4 || prov === 5) {
    row.cl_pool = 9; row.cl_files = 1;
    row.cls = [{ n: 7700000 + i, d: '2026-06-01', s: 'a subject',
                 m: prov === 3 ? 'touched' : (prov === 4 ? 'exact' : 'declares'),
                 b: [] }];
  }
  // Found by searching commit messages, because nothing touched the file.
  // Its own owner so the harness can isolate it: the file's denominator is
  // the thing being asserted, and it must not be printed for these.
  // The floor reached over diffs nobody opened. Its own owner, because the
  // assertion is that this row keeps a way out that the other weak rows do
  // not need: nothing here was searched, so a lookup can still answer it.
  if (prov === 7) {
    row.cl_pool = 147; row.cl_files = 1; row.no_diffs = 1;
    row.owner = 'budget';
    row.cls = [{ n: 7700000 + i, d: '2026-06-01', s: 'a subject',
                 m: 'touched', b: [] }];
  }
  if (prov === 6) {
    row.cl_pool = 0; row.cl_files = 1; row.cl_by_message = 1;
    row.owner = 'msg';
    row.cls = [{ n: 7700000 + i, d: '2026-06-01', s: 'a subject',
                 m: 'described', b: [] }];
  }
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

// Every row states its own values, whether or not the row above says the
// same thing. This table sorts and filters, so "same as above" is a fact
// about the current view rather than about the finding: a row has to stand on
// its own -- searchable, copyable, and correct once the run is sorted apart.
out.everyRowStatesItsCause =
  (els.tb.innerHTML.match(/>Shipped, then flag retired</g) || []).length > 90;
// The path carries <wbr> break points, so it is matched across one of them.
out.everyRowStatesItsPath =
  (els.tb.innerHTML.match(/public\/<wbr>common/g) || []).length > 90;
// And no cell is dressed differently from the one holding the same value.
out.noCellIsMarkedAsARepeat = !/\brep\b/.test(els.tb.innerHTML);

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
// `closest` honours the selector, because the page asks it two different
// questions on the same click -- "is this the lookup button" and "is this a
// row" -- and a stub that answers `row` to both makes a click on empty table
// space look like a click on the button.
const row = new El('tr'); row.className = 'row'; row.dataset.i = '1';
const clickOn = sel => ({ target: { closest: q => (q === sel ? row : null) } });
els.tb.listeners['click'].forEach(f => f(clickOn('tr.row-t')));
out.detailsAfterClick = detailRows.length;
out.detailHasEvidence = detailRows.length > 0 &&
  detailRows[0].innerHTML.includes('flag_retired_on') &&
  detailRows[0].innerHTML.includes('base severity 75');

// Collapse.
row.nextElementSibling = detailRows[0];
els.tb.listeners['click'].forEach(f => f(clickOn('tr.row-t')));
out.detailRemovedOnSecondClick = detailRows[0].removed === true;

// Paging.
els.more.listeners['click'].forEach(f => f());
out.rowsAfterShowMore = els.tb.trCount;

// The evidence filter, and the distinction the floor depends on. A row whose
// only CLs are `touched` lists reviews and explains nothing, so "Has a CL"
// must not return it -- otherwise the fallback quietly inflates the one count
// a reader uses to decide what is already understood.
// The search box still holds the word typed above, and `match` is an AND of
// every control -- so a stale query silently narrows the counts asserted here.
els.q.value = '';
const byEvidence = v => {
  els.fp.value = v;
  els.fp.listeners['change'].forEach(f => f());
  return els.cnt.textContent;
};
out.hasCl = byEvidence('cl');
out.exactOnly = byEvidence('exact');
out.weakOnly = byEvidence('weak');
out.weakRowClass = /class="row-t p-weak"/.test(els.tb.innerHTML);
out.weakRowIsNotCl = !/class="row-t p-cl"/.test(els.tb.innerHTML);

// Expand the first of them: the CLs have to be there, under a sentence saying
// they are leads. A badge alone is skimmed past.
detailRows = [];
const weakRow = new El('tr');
weakRow.className = 'row'; weakRow.dataset.i = '0';
els.tb.listeners['click'].forEach(
  f => f({ target: { closest: q => (q === 'tr.row-t' ? weakRow : null) } }));
const weakHtml = detailRows.length ? detailRows[0].innerHTML : '';
out.weakDetailListsTheCl = /7700\d{3}/.test(weakHtml);
out.weakDetailSaysLead = weakHtml.includes('Leads, not a citation');
out.weakDetailBadge = /ev-touched/.test(weakHtml);

// A row whose diffs the budget declined is not a row that was searched and
// came back empty. Filling it with leads made it read as exhausted and took
// its remedy with it, because both the sentence and the button lived in the
// branch that runs only when there are no CLs at all.
els.q.value = '';
els.fo.value = 'budget';
els.fo.listeners['change'].forEach(f => f());
detailRows = [];
const budgetRow = new El('tr');
budgetRow.className = 'row'; budgetRow.dataset.i = '0';
els.tb.listeners['click'].forEach(
  f => f({ target: { closest: q => (q === 'tr.row-t' ? budgetRow : null) } }));
const budgetHtml = detailRows.length ? detailRows[0].innerHTML : '';
out.budgetRowSaysNothingWasRead = budgetHtml.includes('Nothing here was read');
out.budgetRowNamesThePool = /147 CLs touched/.test(budgetHtml);
// Named as the flag that exists. `--gerrit-budget` belonged to a `why`
// command that was removed, and the page went on telling readers to re-run it.
out.budgetRowOffersTheRemedy = /--click-budget/.test(budgetHtml);
els.fo.value = '';
els.fo.listeners['change'].forEach(f => f());
els.fp.value = 'weak';
els.fp.listeners['change'].forEach(f => f());

// ...and a row that is actually explained carries no such disclaimer.
byEvidence('exact');
detailRows = [];
const exactRow = new El('tr');
exactRow.className = 'row'; exactRow.dataset.i = '0';
els.tb.listeners['click'].forEach(
  f => f({ target: { closest: q => (q === 'tr.row-t' ? exactRow : null) } }));
const exactHtml = detailRows.length ? detailRows[0].innerHTML : '';
out.exactDetailListsTheCl = /7700\d{3}/.test(exactHtml);
out.exactDetailSaysLead = exactHtml.includes('Leads, not a citation');
byEvidence('');

// A CL reached by its commit message never entered the file search, so the
// panel must not print "N of M merged CLs touched this file" over it. The
// fixture gives those rows their own owner because that count is exactly what
// is under test and it has to be isolated to be seen.
els.fo.value = 'msg';
els.fo.listeners['change'].forEach(f => f());
out.messageRowCount = els.cnt.textContent;
detailRows = [];
const msgRow = new El('tr');
msgRow.className = 'row'; msgRow.dataset.i = '0';
els.tb.listeners['click'].forEach(
  f => f({ target: { closest: q => (q === 'tr.row-t' ? msgRow : null) } }));
const msgHtml = detailRows.length ? detailRows[0].innerHTML : '';
out.messageDetailSaysHow = msgHtml.includes('found by commit message');
out.messageDetailHidesTheDenominator = !/merged CLs touched/.test(msgHtml);
out.messageDetailListsTheCl = /7700\d{3}/.test(msgHtml);
els.fo.value = '';
els.fo.listeners['change'].forEach(f => f());

console.log(JSON.stringify(out));
