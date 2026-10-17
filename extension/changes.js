// What changed on the page since the user's last click or key press, for "what changed?".
// Removed content is read as it goes; everything else is read when asked, so only what is
// still on the page and visible is reported. Uses helpers from grounding.js and context.js.

const CHANGE_RECORD_LIMIT = 300;
const CHANGE_ITEM_LIMIT = 20;
const CHANGE_TEXT_LIMIT = 200;
const EDITABLE = '[contenteditable]:not([contenteditable=false])';
const WATCHED_ATTRIBUTES = ['class', 'style', 'hidden', 'open', 'aria-hidden', 'aria-expanded'];

// Typed text lives in fields and editable regions; changes there are never recorded.
function inEditable(node) {
  const el = node.nodeType === 1 ? node : node.parentElement;
  return !el || !!el.closest(`${NO_TEXT}, ${EDITABLE}`);
}

// Text of a node that was just removed: not connected, so safeText's visibility check cannot run.
function removedText(node) {
  if (node.nodeType === 3) return clip(node.data, CHANGE_TEXT_LIMIT);
  if (node.nodeType !== 1 || node.matches(`${NO_TEXT}, ${EDITABLE}`)) return '';
  const walker = node.ownerDocument.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  let out = '';
  for (let n = walker.nextNode(); n && out.length <= CHANGE_TEXT_LIMIT; n = walker.nextNode()) {
    if (!n.parentElement.closest(`${NO_TEXT}, ${EDITABLE}`)) out += n.data + ' ';
  }
  return clip(out, CHANGE_TEXT_LIMIT);
}

// Class changes made only by our own grounding markers are not page changes.
function onlyMarkers(before, after) {
  const own = (v) => (v || '').split(/\s+/).filter((c) => c && !c.startsWith(MARKER_PREFIX)).sort().join(' ');
  return own(before) === own(after);
}

function createChangeTracker(doc, now = () => Date.now()) {
  let since = now();
  let records = []; // {kind, el} or {kind: 'removed', text}, each with time t

  const push = (rec) => {
    records.push(rec);
    if (records.length > CHANGE_RECORD_LIMIT) records.splice(0, records.length - CHANGE_RECORD_LIMIT);
  };

  function onMutations(list) {
    const t = now();
    for (const m of list) {
      if (inEditable(m.target)) continue;
      if (m.type === 'attributes') {
        if (m.attributeName !== 'class' || !onlyMarkers(m.oldValue, m.target.getAttribute('class'))) push({ kind: 'attr', el: m.target, t });
      } else if (m.type === 'characterData') {
        push({ kind: 'text', el: m.target.parentElement, t });
      } else {
        for (const n of m.addedNodes) {
          if (n.nodeType === 1) push({ kind: 'added', el: n, t });
          else if (n.nodeType === 3 && n.data.trim()) push({ kind: 'text', el: m.target, t });
        }
        for (const n of m.removedNodes) {
          const text = removedText(n);
          if (text) push({ kind: 'removed', text, t });
        }
      }
    }
  }

  const observer = new doc.defaultView.MutationObserver(onMutations);
  observer.observe(doc.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: WATCHED_ATTRIBUTES,
    attributeOldValue: true,
  });

  function reset() {
    observer.takeRecords(); // changes from before this click or key press are not its effect
    records = [];
    since = now();
  }

  // Newest first. A change inside newly added content adds nothing; a class or style change on a
  // big container (body, a page wrapper) must not hide the real changes inside it, so only added
  // content absorbs what it contains.
  function report() {
    onMutations(observer.takeRecords());
    const t = now();
    const latest = new Map();
    const removed = [];
    for (const r of records) {
      if (r.kind === 'removed') removed.push(r);
      else if (r.el && r.el !== doc.body && r.el !== doc.documentElement && r.el.isConnected && isVisible(r.el)) latest.set(r.el, r);
    }
    const added = [...latest.values()].filter((r) => r.kind === 'added').map((r) => r.el);
    const outer = [...latest.values()].filter((r) => !added.some((e) => e !== r.el && e.contains(r.el)));
    const items = [...outer, ...removed]
      .sort((a, b) => b.t - a.t)
      .map((r) => {
        const secondsAgo = Math.round((t - r.t) / 1000);
        if (r.kind === 'removed') return { kind: 'removed', text: r.text, secondsAgo };
        const text = safeText(r.el, CHANGE_TEXT_LIMIT) || accessibleName(r.el);
        return text && { kind: r.kind, id: elementId(r.el), tag: r.el.tagName.toLowerCase(), role: r.el.getAttribute('role'), text, secondsAgo };
      })
      .filter(Boolean)
      .slice(0, CHANGE_ITEM_LIMIT);
    return { sinceSeconds: Math.round((t - since) / 1000), items };
  }

  for (const type of ['click', 'keydown']) doc.defaultView.addEventListener(type, reset, { capture: true });
  return { report, reset };
}

if (typeof module !== 'undefined') module.exports = { createChangeTracker, removedText };
