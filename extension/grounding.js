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

// The document of a same-origin frame, or null: a cross-origin frame cannot be read (and is masked).
function frameDocument(frame) {
  try {
    return frame.contentDocument || null;
  } catch {
    return null;
  }
}

// doc and the documents of its same-origin frames, nested ones included.
function frameDocs(doc) {
  const docs = [doc];
  for (const f of doc.querySelectorAll('iframe, frame')) {
    const d = frameDocument(f);
    if (d && d.body) docs.push(...frameDocs(d));
  }
  return docs;
}

// Every element of the page, same-origin frames included.
function allElements(doc) {
  return frameDocs(doc).flatMap((d) => (d.body ? Array.from(d.body.querySelectorAll('*')) : []));
}

// Bounding rect in the top viewport's CSS px: a frame's content is offset by the frame's content box.
function topRect(el) {
  const r = el.getBoundingClientRect();
  let [x, y] = [r.x, r.y];
  for (let w = el.ownerDocument?.defaultView; w && w.frameElement; w = w.parent) {
    const f = w.frameElement;
    const fr = f.getBoundingClientRect();
    const cs = f.ownerDocument.defaultView.getComputedStyle(f);
    x += fr.x + f.clientLeft + (parseFloat(cs.paddingLeft) || 0);
    y += fr.y + f.clientTop + (parseFloat(cs.paddingTop) || 0);
  }
  return [x, y, r.width, r.height];
}

// shortcut: caller passes allElements(document); open shadow roots are not walked yet.
function snapshot(elements) {
  return Array.from(elements, (el) => ({
    id: elementId(el),
    tag: el.tagName.toLowerCase(),
    htmlId: el.id || null,
    rect: topRect(el),
  }));
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

if (typeof module !== 'undefined')
  module.exports = { elementId, snapshot, elementById, markElements, clearMarkers, MARKER_PREFIX, frameDocument, frameDocs, allElements, topRect };
