// Real DOM (jsdom): what the user typed must never appear in the data sent to the model.
const test = require('node:test');
const assert = require('node:assert');
const { JSDOM } = require('jsdom');

const { window } = new JSDOM(`<body><main>
  <h1>Checkout</h1>
  <form aria-label="Teslimat">
    <label for="name">Ad Soyad</label><input id="name" required>
    <label for="pw">Parola</label><input id="pw" type="password">
    <label for="note">Not</label><textarea id="note"></textarea>
    <select id="city"><option>Ankara</option><option>TYPED-SELECT</option></select>
    <div id="editor" contenteditable="true">TYPED-EDITABLE</div>
    <button type="button">Devam</button>
  </form>
</main></body>`);
const { document } = window;

// jsdom has no layout or editing model: treat everything as visible and derive isContentEditable.
window.Element.prototype.checkVisibility = () => true;
Object.defineProperty(window.HTMLElement.prototype, 'isContentEditable', {
  get() {
    return !!this.closest('[contenteditable]:not([contenteditable=false])');
  },
});
globalThis.NodeFilter = window.NodeFilter;
const ids = new WeakMap();
globalThis.elementId = (el) => ids.get(el) || (ids.set(el, `e_${Math.random()}`), ids.get(el));

const { describeElement, pageOutline, formContext } = require('./context.js');

document.getElementById('name').value = 'TYPED-NAME';
document.getElementById('pw').value = 'TYPED-PASSWORD';
document.getElementById('note').value = 'TYPED-NOTE';
document.getElementById('city').selectedIndex = 1;

test('typed text never reaches element, outline or form data', () => {
  const form = document.querySelector('form');
  const sent = JSON.stringify([
    describeElement(form),
    describeElement(document.getElementById('name')),
    describeElement(document.getElementById('editor')),
    pageOutline(document),
    formContext(document.getElementById('name')),
  ]);
  for (const typed of ['TYPED-NAME', 'TYPED-PASSWORD', 'TYPED-NOTE', 'TYPED-SELECT', 'TYPED-EDITABLE']) {
    assert.ok(!sent.includes(typed), `${typed} leaked`);
  }
  // Page text still gets through, so the test is not passing on empty output.
  assert.ok(sent.includes('Ad Soyad') && sent.includes('Checkout') && sent.includes('Devam'));
});

test('form data says whether a field is filled, never what', () => {
  const fields = formContext(document.getElementById('name')).fields;
  const byLabel = Object.fromEntries(fields.map((f) => [f.label, f]));
  assert.strictEqual(byLabel['Ad Soyad'].filled, true);
  assert.strictEqual(byLabel['Ad Soyad'].isTarget, true);
  assert.strictEqual(byLabel['Parola'].sensitive, true);
});
