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

const { elementId: _unused, ...frameHelpers } = require('./grounding.js');
Object.assign(globalThis, frameHelpers); // content scripts share one scope
const { describeElement, pageOutline, formContext, tableContext, sensitiveRects } = require('./context.js');

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

test('table data: cell texts, marked headers, sizes and the target cell, never field values', () => {
  document.body.insertAdjacentHTML(
    'beforeend',
    `<table id="orders"><caption>Siparişler</caption>
      <tr><th>No</th><th>Tutar</th><th>Not</th></tr>
      <tr><td>1</td><td id="amount">120 TL</td><td><input id="memo"></td></tr>
      <tr><td>2</td><td>80 TL</td><td>hediye</td></tr>
    </table>`,
  );
  document.getElementById('memo').value = 'TYPED-MEMO';
  const t = tableContext(document.getElementById('amount'));
  assert.strictEqual(t.caption, 'Siparişler');
  assert.deepStrictEqual(t.rows[0], { cells: ['No', 'Tutar', 'Not'], headers: [0, 1, 2] });
  assert.deepStrictEqual(t.rows[1], { cells: ['1', '120 TL', ''] });
  assert.deepStrictEqual([t.rowCount, t.columnCount, t.target], [3, 3, [1, 1]]);
  assert.ok(!JSON.stringify(t).includes('TYPED-MEMO'));
  assert.strictEqual(tableContext(document.querySelector('h1')), null);
});

test('same-origin frames are read and offset; cross-origin frames are masked whole', () => {
  const frame = document.createElement('iframe');
  document.body.append(frame);
  frame.getBoundingClientRect = () => ({ x: 100, y: 50, width: 400, height: 300 });
  const inner = frame.contentDocument;
  frame.contentWindow.Element.prototype.checkVisibility = () => true; // each frame has its own prototypes
  inner.body.innerHTML = '<h2>Gömülü form</h2><input id="otp" autocomplete="one-time-code"><button id="go">Gönder</button>';
  inner.getElementById('otp').value = 'TYPED-OTP';
  inner.getElementById('otp').getBoundingClientRect = () => ({ x: 10, y: 20, width: 80, height: 30 });
  const other = document.createElement('iframe');
  document.body.append(other);
  Object.defineProperty(other, 'contentDocument', { get: () => null }); // what a cross-origin frame looks like
  other.getBoundingClientRect = () => ({ x: 0, y: 400, width: 300, height: 100 });

  assert.ok(allElements(document).includes(inner.getElementById('go')));
  assert.deepStrictEqual(topRect(inner.getElementById('otp')), [110, 70, 80, 30]);
  assert.deepStrictEqual(sensitiveRects(allElements(document)).sort(), [[0, 400, 300, 100], [110, 70, 80, 30]]);
  const outline = JSON.stringify(pageOutline(document));
  assert.ok(outline.includes('Gömülü form') && outline.includes('Gönder'));
  assert.ok(!outline.includes('TYPED-OTP'));
  assert.match(describeElement(inner.getElementById('go')).text, /Gönder/);
  frame.remove();
  other.remove();
});
