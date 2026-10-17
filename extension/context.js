// Structured, value-free description of one element for the coordinator, plus the
// geometry for a masked screenshot crop. Field values are never read.

const TEXT_LIMIT = 300;
const IMAGE_LIMIT = 20;
const SENSITIVE_AUTOCOMPLETE = /\b(cc-|one-time-code|current-password|new-password)/i;
const SENSITIVE_HINT =
  /(passw|parola|şifre|sifre|otp|one.?time|tek kullanımlık|doğrulama kodu|dogrulama kodu|verification code|security code|güvenlik kodu|cvv|cvc|card.?num|kart.?n|iban|\bpin\b)/i;

// Text the user typed lives in form fields and contenteditable regions; innerText would include it.
const NO_TEXT = 'input, textarea, select, script, style, noscript';

function clip(text, limit = TEXT_LIMIT) {
  const t = (text || '').replace(/\s+/g, ' ').trim();
  return t.length > limit ? t.slice(0, limit) + '…' : t;
}

// Visible page text under root, skipping fields and editable regions. Never use innerText for model data.
function safeText(root, limit = TEXT_LIMIT) {
  if (!root || root.isContentEditable || root.matches(NO_TEXT)) return '';
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let out = '';
  for (let n = walker.nextNode(); n && out.length <= limit; n = walker.nextNode()) {
    const p = n.parentElement;
    if (!p || p.isContentEditable || p.closest(NO_TEXT) || !isVisible(p)) continue;
    out += n.data + ' ';
  }
  return clip(out, limit);
}

// password, OTP and card fields: their value, and their pixels, must never reach the model.
function isSensitiveField(el) {
  const tag = el.tagName.toLowerCase();
  if (tag !== 'input' && tag !== 'textarea') return false;
  if ((el.getAttribute('type') || '').toLowerCase() === 'password') return true;
  if (SENSITIVE_AUTOCOMPLETE.test(el.getAttribute('autocomplete') || '')) return true;
  const hints = ['name', 'id', 'aria-label', 'placeholder'].map((a) => el.getAttribute(a) || '');
  if (el.labels) for (const l of el.labels) hints.push(l.textContent || ''); // local regex check only
  return hints.some((h) => SENSITIVE_HINT.test(h));
}

function idrefText(el, attr) {
  const ids = (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean);
  return clip(ids.map((id) => safeText(el.ownerDocument.getElementById(id))).join(' '));
}

function describeElement(el) {
  const attr = (name) => el.getAttribute(name);
  const href = attr('href');
  let link = null;
  if (href) {
    try {
      const u = new URL(href, el.baseURI);
      link = u.origin + u.pathname; // query and fragment may carry tokens
    } catch {
      link = null;
    }
  }
  const sensitive = isSensitiveField(el);
  return {
    tag: el.tagName.toLowerCase(),
    role: attr('role'),
    type: attr('type'),
    ariaLabel: attr('aria-label'),
    labelledBy: idrefText(el, 'aria-labelledby'),
    describedBy: idrefText(el, 'aria-describedby'),
    title: attr('title'),
    alt: attr('alt'),
    placeholder: attr('placeholder'),
    link,
    labels: el.labels ? Array.from(el.labels, (l) => safeText(l)) : [],
    text: sensitive ? '' : safeText(el),
    images: Array.from(el.querySelectorAll('img, svg'), (i) => clip(i.getAttribute('alt') || i.getAttribute('aria-label') || i.querySelector?.('title')?.textContent || '', 80)).filter(Boolean).slice(0, IMAGE_LIMIT),
    nearby: {
      before: safeText(el.previousElementSibling, 150),
      after: safeText(el.nextElementSibling, 150),
      parent: safeText(el.parentElement),
    },
    states: {
      disabled: el.disabled === true || attr('aria-disabled') === 'true',
      checked: el.checked === true || attr('aria-checked') === 'true',
      expanded: attr('aria-expanded'),
      pressed: attr('aria-pressed'),
      required: el.required === true || attr('aria-required') === 'true',
    },
    sensitive,
  };
}

const OUTLINE_CONTROL_LIMIT = 150;
const LANDMARKS =
  'header, nav, main, aside, footer, form, dialog[open], [role=banner], [role=navigation], [role=main], [role=complementary], [role=contentinfo], [role=search], [role=dialog], [role=alertdialog], [role=region][aria-label]';
// shortcut: listeners added with addEventListener are invisible here; only markup hints mark a control.
const CONTROLS =
  'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=combobox], [role=switch], [onclick], [tabindex]:not([tabindex="-1"])';

// Rough accessible name from markup; never from a field value.
function accessibleName(el) {
  const attr = (n) => (el.getAttribute(n) || '').trim();
  return clip(
    attr('aria-label') ||
      idrefText(el, 'aria-labelledby') ||
      (el.labels ? Array.from(el.labels, (l) => safeText(l)).join(' ') : '') ||
      safeText(el, 100) ||
      attr('title') ||
      attr('alt') ||
      attr('placeholder') ||
      Array.from(el.querySelectorAll('img[alt], svg title'), (i) => i.getAttribute('alt') || i.textContent).join(' '),
    100,
  );
}

function isVisible(el) {
  return el.checkVisibility ? el.checkVisibility() : el.getClientRects().length > 0;
}

// Value-free outline of the page for "summarize this page".
function pageOutline(doc) {
  const [vw, vh] = [doc.defaultView.innerWidth, doc.defaultView.innerHeight];
  const inView = (el) => {
    const [x, y, w, h] = topRect(el);
    return y + h > 0 && x + w > 0 && y < vh && x < vw;
  };
  const visible = (sel) => visibleMatches(doc, sel);
  const found = visible(CONTROLS).map((el) => ({ el, inViewport: inView(el) }));
  found.sort((a, b) => b.inViewport - a.inViewport); // stable: document order within each group
  // Names walk text nodes, so only the controls that are sent get one.
  const controls = found.slice(0, OUTLINE_CONTROL_LIMIT).map(({ el, inViewport }) => {
    const name = accessibleName(el);
    return {
      id: elementId(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      type: el.getAttribute('type'),
      name,
      unlabeled: !name,
      inViewport,
      sensitive: isSensitiveField(el),
    };
  });
  const main = doc.querySelector('main, [role=main]') || doc.body;
  return {
    headings: pageHeadings(doc),
    landmarks: pageLandmarks(doc),
    alerts: pageAlerts(doc),
    controls,
    controlCount: found.length,
    mainText: safeText(main, 1500),
  };
}

const HEADINGS = 'h1, h2, h3, h4, h5, h6, [role=heading]';
// Matches in doc and its same-origin frames.
const visibleMatches = (doc, sel) => frameDocs(doc).flatMap((d) => Array.from(d.querySelectorAll(sel))).filter(isVisible);

function pageHeadings(doc) {
  return visibleMatches(doc, HEADINGS).map((el) => ({
    id: elementId(el),
    level: Number(el.getAttribute('aria-level') || el.tagName.slice(1)) || null,
    text: safeText(el, 120),
  }));
}

function pageLandmarks(doc) {
  return visibleMatches(doc, LANDMARKS).map((el) => ({
    id: elementId(el),
    role: el.getAttribute('role') || el.tagName.toLowerCase(),
    name: clip(el.getAttribute('aria-label') || idrefText(el, 'aria-labelledby'), 80),
  }));
}

function pageAlerts(doc) {
  return visibleMatches(doc, '[role=alert], [role=status], [aria-live]:not([aria-live=off])')
    .map((el) => safeText(el, 200))
    .filter(Boolean);
}

const BLOCK_LIMIT = 40;
const BLOCK_SPLIT_MIN_CHARS = 400; // a block with less text is small enough to name as one part

// Visible parts of the page in document order: start with the body and keep splitting the block
// with the most text into its children, skipping single-child wrappers, until BLOCK_LIMIT.
function pageBlocks(doc, limit = BLOCK_LIMIT) {
  const sizes = new Map();
  // Length only, to rank blocks; the content sent is read with safeText.
  // A same-origin frame is a block whose parts are its body's children.
  const inner = (el) => (el.matches('iframe, frame') ? frameDocument(el)?.body : null);
  const size = (el) => sizes.get(el) ?? sizes.set(el, ((inner(el) || el).textContent || '').length).get(el);
  const parts = (el) =>
    Array.from((inner(el) || el).children).filter((c) => !c.matches(NO_TEXT) && size(c) > 20 && isVisible(c));
  const unwrap = (el) => {
    let p = parts(el);
    while (p.length === 1) [el, p] = [p[0], parts(p[0])];
    return { el, parts: p };
  };
  const blocks = [unwrap(doc.body)];
  for (;;) {
    let best = -1;
    blocks.forEach((b, i) => {
      if (b.parts.length > 1 && size(b.el) >= BLOCK_SPLIT_MIN_CHARS && (best < 0 || size(b.el) > size(blocks[best].el))) best = i;
    });
    if (best < 0 || blocks.length - 1 + blocks[best].parts.length > limit) break;
    blocks.splice(best, 1, ...blocks[best].parts.map(unwrap));
  }
  return blocks.map(({ el }) => el);
}

// Value-free page structure for the AI section list.
function pageSections(doc) {
  return {
    headings: pageHeadings(doc),
    landmarks: pageLandmarks(doc),
    blocks: pageBlocks(doc).map((el) => ({
      id: elementId(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      heading: safeText(el.matches(HEADINGS) ? el : el.querySelector(HEADINGS), 100),
      text: safeText(el, 200),
    })),
  };
}

const FORM_FIELD_LIMIT = 60;
const FIELDS =
  'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]), select, textarea, [role=textbox], [role=combobox], [role=checkbox], [role=radio], [role=switch], [role=spinbutton], [role=listbox], [contenteditable]:not([contenteditable=false])';
const VALIDITY_FLAGS = ['valueMissing', 'typeMismatch', 'patternMismatch', 'tooShort', 'tooLong', 'rangeUnderflow', 'rangeOverflow', 'stepMismatch', 'badInput'];

// Value-free description of the form around el: labels, required/filled/invalid state, error texts.
// validationMessage is not used: Chrome's message can quote what the user typed.
function formContext(el) {
  const doc = el.ownerDocument;
  const container = el.closest('form, [role=form], fieldset') || doc.body;
  const fields = Array.from(container.querySelectorAll(FIELDS)).filter(isVisible).slice(0, FORM_FIELD_LIMIT);
  const field = (f) => {
    const validity = f.validity ? VALIDITY_FLAGS.filter((k) => f.validity[k]) : [];
    const userInvalid = f.matches(':user-invalid') || f.getAttribute('aria-invalid') === 'true';
    const isToggle = f.type === 'checkbox' || f.type === 'radio';
    return {
      id: elementId(f),
      tag: f.tagName.toLowerCase(),
      type: f.getAttribute('type'),
      role: f.getAttribute('role'),
      label: accessibleName(f),
      placeholder: f.getAttribute('placeholder'),
      required: f.required === true || f.getAttribute('aria-required') === 'true',
      // whether, never what; a checkbox's value is always set, its state is in checked
      filled: typeof f.value === 'string' && !isToggle ? f.value !== '' : null,
      checked: isToggle ? f.checked : null,
      disabled: f.disabled === true || f.getAttribute('aria-disabled') === 'true',
      invalid: userInvalid,
      problems: userInvalid ? validity : [],
      errorText: clip(idrefText(f, 'aria-errormessage') || (userInvalid ? idrefText(f, 'aria-describedby') : ''), 200),
      sensitive: isSensitiveField(f),
      isTarget: f === el,
    };
  };
  const visibleIn = (sel) => Array.from(container.querySelectorAll(sel)).filter(isVisible);
  return {
    name: clip(
      container.getAttribute('aria-label') || idrefText(container, 'aria-labelledby') || safeText(container.querySelector('legend, h1, h2, h3')),
      120,
    ),
    wholePage: container === doc.body,
    fields: fields.map(field),
    buttons: visibleIn('button, input[type=submit], input[type=button], [role=button]').map((b) => accessibleName(b)).filter(Boolean).slice(0, 15),
    messages: visibleIn('[role=alert], [role=status], [aria-live]:not([aria-live=off]), [class*=error i], [class*=invalid i]')
      .filter((m) => !m.matches(FIELDS))
      .map((m) => safeText(m, 200))
      .filter(Boolean)
      .slice(0, 10),
    rect: topRect(container),
  };
}

const TABLES = 'table, [role=table], [role=grid], [role=treegrid]';
const TABLE_CELLS = 'th, td, [role=cell], [role=gridcell], [role=columnheader], [role=rowheader]';
const TABLE_ROW_LIMIT = 30;
const TABLE_COL_LIMIT = 12;

// Value-free description of the table around el (or inside it): caption, the first rows as cell
// texts, which cells are marked as headers, sizes, and the cell el is in. Null if there is none.
function tableContext(el) {
  const table = el.closest(TABLES) || el.querySelector(TABLES);
  if (!table) return null;
  const rows = Array.from(table.querySelectorAll('tr, [role=row]')).filter((r) => r.closest(TABLES) === table && isVisible(r));
  const cellsOf = (r) => Array.from(r.children).filter((c) => c.matches(TABLE_CELLS));
  let target = null;
  const shown = rows.slice(0, TABLE_ROW_LIMIT).map((r, i) => {
    const cells = cellsOf(r).slice(0, TABLE_COL_LIMIT);
    const headers = [];
    const texts = cells.map((c, j) => {
      if (c.contains(el)) target = [i, j];
      if (c.tagName === 'TH' || /header/.test(c.getAttribute('role') || '')) headers.push(j);
      return safeText(c, 80);
    });
    return headers.length ? { cells: texts, headers } : { cells: texts };
  });
  return {
    caption: clip(
      table.getAttribute('aria-label') || idrefText(table, 'aria-labelledby') || safeText(table.querySelector('caption')),
      120,
    ),
    rows: shown,
    rowCount: rows.length,
    columnCount: Math.max(0, ...rows.map((row) => cellsOf(row).length)),
    target,
    rect: topRect(table),
  };
}

// Move keyboard focus (and so NVDA's browse-mode cursor) to el. Non-focusable elements get a
// temporary tabindex=-1 that is removed again when focus leaves. Returns whether focus landed.
function focusElement(el) {
  el.scrollIntoView({ block: 'center' });
  if (el.tabIndex < 0 && !el.hasAttribute('tabindex')) {
    el.setAttribute('tabindex', '-1');
    el.addEventListener('blur', () => el.removeAttribute('tabindex'), { once: true });
  }
  el.focus({ preventScroll: true });
  return el.ownerDocument.activeElement === el;
}

// Open or closed shadow root; chrome.dom reaches closed ones from a content script.
function shadowRootOf(el) {
  return globalThis.chrome?.dom?.openOrClosedShadowRoot?.(el) ?? el.shadowRoot ?? null;
}

function sensitiveRects(elements) {
  const rects = [];
  for (const el of elements) {
    const shadow = shadowRootOf(el);
    if (shadow) rects.push(...sensitiveRects(shadow.querySelectorAll('*')));
    // Payment providers put card fields in cross-origin frames we cannot inspect, so those are masked
    // whole; a same-origin frame's own fields are in elements and masked one by one.
    const frame = el.matches('iframe, frame');
    if (frame ? frameDocument(el) : !isSensitiveField(el)) continue;
    const r = topRect(el);
    if (r[2] > 0 && r[3] > 0) rects.push(r);
  }
  return rects;
}

// Crop around rect (CSS px) with margin, clamped to the viewport, in screenshot pixels.
// Returns null when the element is not visible in the viewport.
function cropBox(rect, viewport, scale, margin = 120) {
  const [x, y, w, h] = rect;
  const [vw, vh] = viewport;
  if (x + w <= 0 || y + h <= 0 || x >= vw || y >= vh || w <= 0 || h <= 0) return null;
  const left = Math.max(0, x - margin);
  const top = Math.max(0, y - margin);
  const right = Math.min(vw, x + w + margin);
  const bottom = Math.min(vh, y + h + margin);
  return [left, top, right - left, bottom - top].map((v) => Math.round(v * scale));
}

if (typeof module !== 'undefined')
  module.exports = { NO_TEXT, clip, safeText, accessibleName, isVisible, isSensitiveField, describeElement, pageOutline, pageAlerts, pageSections, formContext, tableContext, focusElement, sensitiveRects, cropBox };
