/* Run the page's own answer renderer, and report what it produced.
 *
 * The renderer takes text written by a model and puts it into `innerHTML`, so
 * two different things have to hold at once: markdown has to come out as
 * markup, and everything else has to come out as text. Reading the source
 * cannot tell you either; running it can.
 *
 * The two functions are lifted out of a generated report.html rather than
 * copied here, so this tests the renderer that ships. Renaming them fails
 * loudly, which is the right failure -- a copy would go on passing while the
 * page did something else.
 */
'use strict';
const fs = require('fs');

const page = fs.readFileSync(process.argv[2], 'utf8');
const start = page.indexOf('function askInline');
const end = page.indexOf('function askSend');
if (start < 0 || end < 0 || end < start) {
  console.error('could not find askInline/askProse in the page');
  process.exit(2);
}
const source = page.slice(start, end);

/* What the page's own `esc` does: set textContent, read innerHTML back. Only
 * the three characters a text node escapes -- the renderer never builds an
 * attribute, so quotes are not among them. */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const askProse = new Function('esc', source + '\nreturn askProse;')(esc);

const cases = {
  bold: askProse('There are **120** findings.'),
  bullets: askProse('Read these:\n\n- one thing\n- another thing'),
  starBullets: askProse('* first\n* second'),
  inlineCode: askProse('Start at `mojo_field:blink.mojom.Params.x`.'),
  fenced: askProse('Try this:\n\n```python\nprint(len(F))\n```'),
  paragraphs: askProse('First para.\n\nSecond para.'),
  softBreak: askProse('line one\nline two'),
  empty: askProse(''),
  // The one that is not about formatting. A model's answer is text arriving
  // from outside, and it lands in innerHTML.
  markup: askProse('<img src=x onerror="alert(1)"> and <b>bold</b>'),
  markupInCode: askProse('`<script>alert(1)</script>`'),
  markupInFence: askProse('```\n<script>alert(1)</script>\n```'),
  ampersand: askProse('flags & switches'),
};

console.log(JSON.stringify(cases, null, 1));
