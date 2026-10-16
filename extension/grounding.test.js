const test = require('node:test');
const assert = require('node:assert');
const { snapshot, markElements, clearMarkers } = require('./grounding.js');

function fakeElement(tagName, id, rect, classes = []) {
  const set = new Set(classes);
  return {
    tagName,
    id,
    getBoundingClientRect: () => ({ x: rect[0], y: rect[1], width: rect[2], height: rect[3] }),
    classList: {
      add: (c) => set.add(c),
      remove: (c) => set.delete(c),
      [Symbol.iterator]: () => set.values(),
    },
    classes: set,
  };
}

test('snapshot keeps element IDs stable across calls', () => {
  const els = [fakeElement('BUTTON', 'go', [10, 10, 80, 30]), fakeElement('DIV', '', [0, 0, 5, 5])];
  const first = snapshot(els);
  const second = snapshot([els[1], els[0]]);
  assert.deepStrictEqual(first[0], { id: first[0].id, tag: 'button', htmlId: 'go', rect: [10, 10, 80, 30] });
  assert.strictEqual(first[1].htmlId, null);
  assert.strictEqual(second[1].id, first[0].id);
  assert.notStrictEqual(first[0].id, first[1].id);
});

test('markers are added only to wanted IDs and cleared per nonce', () => {
  const a = fakeElement('DIV', '', [0, 0, 1, 1], ['site']);
  const b = fakeElement('DIV', '', [0, 0, 1, 1]);
  const [sa] = snapshot([a, b]);
  markElements([a, b], new Set([sa.id]), 'old');
  markElements([a, b], new Set([sa.id]), 'n1');
  assert.deepStrictEqual([...b.classes], []);
  clearMarkers([a, b], 'n1');
  assert.deepStrictEqual([...a.classes], ['site', `nvai-old-${sa.id}`]);
});
