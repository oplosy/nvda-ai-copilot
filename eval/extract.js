// Builds the extension's reply for each eval case in jsdom with the real extension code, the same
// way content.js does. jsdom has no layout: no screenshots, and every element counts as visible.
// Prints a JSON list; eval/run.py reads it.
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const EXTENSION = path.join(__dirname, '..', 'extension');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'cases.json'), 'utf8'));

function load(file) {
  const { window } = new JSDOM(fs.readFileSync(path.join(__dirname, 'cases', file), 'utf8'), { url: 'https://shop.example/' });
  window.Element.prototype.checkVisibility = () => true;
  Object.defineProperty(window.HTMLElement.prototype, 'isContentEditable', {
    get() {
      return !!this.closest('[contenteditable]:not([contenteditable=false])');
    },
  });
  globalThis.NodeFilter = window.NodeFilter;
  // Fresh extension modules per page: element IDs are per-page state, as in the browser.
  for (const name of ['grounding.js', 'context.js']) delete require.cache[require.resolve(path.join(EXTENSION, name))];
  Object.assign(globalThis, require(path.join(EXTENSION, 'grounding.js'))); // content scripts share one scope
  Object.assign(globalThis, require(path.join(EXTENSION, 'context.js')));
  return window.document;
}

const out = cases.map((c) => {
  const doc = load(c.file);
  const page = { origin: 'https://shop.example', title: doc.title };
  const target = c.target ? doc.querySelector(c.target) : null;
  if (c.target && !target) throw new Error(`${c.id}: no element ${c.target}`);
  const replies = { focus: { focused: true } };
  if (c.task === 'explain') replies.context = { page, element: describeElement(target) };
  if (c.task === 'form') replies.form = { page, form: formContext(target) };
  if (c.task === 'table') replies.table = { page, table: tableContext(target) };
  if (c.task === 'summarize' || c.task === 'find') replies.outline = { page, outline: pageOutline(doc) };
  if (c.task === 'sections') replies.sections = { page, sections: pageSections(doc) };
  const expected = c.expect.element && doc.querySelector(c.expect.element);
  if (c.expect.element && !expected) throw new Error(`${c.id}: no element ${c.expect.element}`);
  return { ...c, targetId: target && elementId(target), expectId: expected ? elementId(expected) : null, replies };
});
process.stdout.write(JSON.stringify(out));
