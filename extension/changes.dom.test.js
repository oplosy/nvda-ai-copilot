// Real DOM (jsdom): the "what changed?" tracker and the page blocks for the AI section list.
const test = require('node:test');
const assert = require('node:assert');
const { JSDOM } = require('jsdom');

const { window } = new JSDOM('<body></body>');
const { document } = window;
// jsdom has no layout or editing model: treat connected elements as visible and derive isContentEditable.
window.Element.prototype.checkVisibility = function () {
  return this.isConnected;
};
Object.defineProperty(window.HTMLElement.prototype, 'isContentEditable', {
  get() {
    return !!this.closest('[contenteditable]:not([contenteditable=false])');
  },
});
globalThis.NodeFilter = window.NodeFilter;
const ids = new WeakMap();
let nextId = 1;
globalThis.elementId = (el) => ids.get(el) || (ids.set(el, `e_${nextId++}`), ids.get(el));
globalThis.MARKER_PREFIX = require('./grounding.js').MARKER_PREFIX;
const context = require('./context.js');
Object.assign(globalThis, context);
const { createChangeTracker } = require('./changes.js');

let clock = 0;
const tracker = createChangeTracker(document, () => clock);

function setPage(html) {
  document.body.innerHTML = html;
  clock += 1000;
  window.dispatchEvent(new window.MouseEvent('click'));
}

test('reports what appeared after the last click, not before', () => {
  setPage('<div id="cart">Sepet boş</div>');
  document.body.insertAdjacentHTML('beforeend', '<p>eski reklam</p>');
  window.dispatchEvent(new window.MouseEvent('click'));
  clock += 2000;
  document.body.insertAdjacentHTML('beforeend', '<div role="dialog"><h2>Ürün sepete eklendi</h2><button>Sepete git</button></div>');
  const { sinceSeconds, items } = tracker.report();
  assert.strictEqual(sinceSeconds, 2);
  assert.strictEqual(items.length, 1); // the button inside the new dialog is not listed again
  assert.deepStrictEqual([items[0].kind, items[0].role, items[0].secondsAgo], ['added', 'dialog', 0]);
  assert.match(items[0].text, /Ürün sepete eklendi/);
  assert.ok(!JSON.stringify(items).includes('eski reklam'));
});

test('typed text and editable regions are never reported', () => {
  setPage('<input id="q"><div id="ed" contenteditable="true">x</div><textarea id="t"></textarea>');
  document.getElementById('q').value = 'TYPED-INPUT';
  document.getElementById('ed').textContent = 'TYPED-EDITABLE';
  document.getElementById('ed').insertAdjacentHTML('beforeend', '<b>TYPED-BOLD</b>');
  document.getElementById('t').value = 'TYPED-TEXTAREA';
  document.getElementById('ed').remove();
  assert.deepStrictEqual(tracker.report().items, []);
});

test('removed content keeps its former text', () => {
  setPage('<div id="err" role="alert">Kart reddedildi</div><div>kalan</div>');
  document.getElementById('err').remove();
  const items = tracker.report().items;
  assert.deepStrictEqual(items.map((i) => [i.kind, i.text]), [['removed', 'Kart reddedildi']]);
});

test('grounding marker classes are ignored, real class changes are reported', () => {
  setPage('<ul id="menu" class="menu"><li>Profil</li><li>Çıkış</li></ul>');
  const menu = document.getElementById('menu');
  menu.classList.add(`${MARKER_PREFIX}abcd-e_1`);
  assert.deepStrictEqual(tracker.report().items, []);
  menu.classList.add('open');
  assert.deepStrictEqual(tracker.report().items.map((i) => [i.kind, i.text]), [['attr', 'Profil Çıkış']]);
});

test('a class change on the body does not hide changes inside it', () => {
  setPage('<main><p id="count">0 ürün</p></main>');
  document.body.classList.add('modal-open');
  document.getElementById('count').textContent = '1 ürün';
  // Replacing the text is a new text node plus the old one removed, so the model hears both values.
  assert.deepStrictEqual(tracker.report().items.map((i) => [i.kind, i.text]), [['text', '1 ürün'], ['removed', '0 ürün']]);
});

test('page blocks split big containers into visible parts in document order', () => {
  const long = (word) => `${word} `.repeat(120);
  setPage(`<div id="app"><div class="wrap">
    <nav>Ana sayfa Kategoriler Kampanyalar Hesabım</nav>
    <main><section><h2>Filtreler</h2>${long('marka')}</section><section>${long('ürün')}</section></main>
    <footer>İletişim ve yasal bilgiler sayfanın altında</footer>
  </div></div>`);
  const blocks = context.pageSections(document).blocks;
  assert.deepStrictEqual(blocks.map((b) => b.tag), ['nav', 'section', 'section', 'footer']);
  assert.strictEqual(blocks[1].heading, 'Filtreler');
  assert.ok(blocks.every((b) => b.id && b.text.length <= 201));
});
