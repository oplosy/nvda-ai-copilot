const test = require('node:test');
const assert = require('node:assert');
const { isSensitiveField, sensitiveRects, cropBox } = require('./context.js');

function field(tagName, attrs = {}, labels = []) {
  return { tagName, getAttribute: (n) => attrs[n] ?? null, labels: labels.map((t) => ({ textContent: t })) };
}

test('password, OTP and card fields are sensitive', () => {
  assert.ok(isSensitiveField(field('INPUT', { type: 'password' })));
  assert.ok(isSensitiveField(field('INPUT', { autocomplete: 'cc-number' })));
  assert.ok(isSensitiveField(field('INPUT', { autocomplete: 'one-time-code' })));
  assert.ok(isSensitiveField(field('INPUT', { name: 'cvv' })));
  assert.ok(isSensitiveField(field('INPUT', {}, ['Kart Numarası'])));
  assert.ok(isSensitiveField(field('INPUT', { placeholder: 'Doğrulama kodu' })));
});

test('ordinary fields and non-fields are not sensitive', () => {
  assert.ok(!isSensitiveField(field('INPUT', { type: 'search', name: 'q' }, ['Ara'])));
  assert.ok(!isSensitiveField(field('INPUT', { name: 'shipping-address' })));
  assert.ok(!isSensitiveField(field('DIV', { 'aria-label': 'password' })));
});

test('cropBox clamps to the viewport and scales', () => {
  assert.deepStrictEqual(cropBox([50, 50, 20, 10], [800, 600], 2, 100), [0, 0, 340, 320]);
  assert.deepStrictEqual(cropBox([700, 550, 50, 40], [800, 600], 1, 100), [600, 450, 200, 150]);
});

test('cropBox is null for elements outside the viewport', () => {
  assert.strictEqual(cropBox([0, 700, 50, 40], [800, 600], 1), null);
  assert.strictEqual(cropBox([-80, 0, 50, 40], [800, 600], 1), null);
  assert.strictEqual(cropBox([10, 10, 0, 0], [800, 600], 1), null);
});

test('sensitive fields, iframes and fields inside shadow roots are masked', () => {
  const at = (el, x) => Object.assign(el, { getBoundingClientRect: () => ({ x, y: 0, width: 10, height: 10 }) });
  const password = at(field('INPUT', { type: 'password' }), 1);
  const iframe = at(field('IFRAME'), 2);
  const hiddenPassword = at(field('INPUT', { type: 'password' }), 3);
  const host = at(field('MY-LOGIN'), 4);
  host.shadowRoot = { querySelectorAll: () => [hiddenPassword] };
  const plain = at(field('INPUT', { name: 'q' }), 5);
  const xs = sensitiveRects([password, iframe, host, plain]).map((r) => r[0]);
  assert.deepStrictEqual(xs.sort(), [1, 2, 3]);
});
