// Element IDs and temporary marker classes for NVDA <-> DOM grounding.
// Chromium exposes the HTML class attribute via IAccessible2, so NVDA can read a marker
// we put on an element. See docs/spike-dom-mapping.md.

const MARKER_PREFIX = 'nvai-';
const elementIds = new WeakMap();
// shortcut: entries are never pruned (a string + WeakRef per element ever seen); prune on navigation if pages get huge.
const elementsById = new Map();
let nextElementId = 1;

// Stable per element for the page's lifetime, so IDs survive DOM re-reads.
function elementId(el) {
  let id = elementIds.get(el);
  if (!id) {
    id = `e_${nextElementId++}`;
    elementIds.set(el, id);
    elementsById.set(id, new WeakRef(el));
  }
  return id;
}

// The live element for an ID, or null if it was removed from the page.
function elementById(id) {
  const el = elementsById.get(id)?.deref();
  return el && el.isConnected ? el : null;
}

// shortcut: caller passes document.body.querySelectorAll('*'); open shadow roots and iframes are not walked yet.
function snapshot(elements) {
  return Array.from(elements, (el) => {
    const r = el.getBoundingClientRect();
    return {
      id: elementId(el),
      tag: el.tagName.toLowerCase(),
      htmlId: el.id || null,
      rect: [r.x, r.y, r.width, r.height],
    };
  });
}

// Nonce per marking round, so stale or page-forged markers are not accepted by the coordinator.
function markElements(elements, wantedIds, nonce) {
  for (const el of elements) {
    const id = elementIds.get(el);
    if (id && wantedIds.has(id)) el.classList.add(`${MARKER_PREFIX}${nonce}-${id}`);
  }
}

function clearMarkers(elements, nonce) {
  const prefix = `${MARKER_PREFIX}${nonce}-`;
  for (const el of elements) {
    for (const c of [...el.classList]) if (c.startsWith(prefix)) el.classList.remove(c);
  }
}

if (typeof module !== 'undefined') module.exports = { snapshot, elementById, markElements, clearMarkers, MARKER_PREFIX };
