// Structured, value-free description of one element for the coordinator, plus the
// geometry for a masked screenshot crop. Field values are never read.

const TEXT_LIMIT = 300;
const SENSITIVE_AUTOCOMPLETE = /\b(cc-|one-time-code|current-password|new-password)/i;
const SENSITIVE_HINT =
  /(passw|parola|şifre|sifre|otp|one.?time|tek kullanımlık|doğrulama kodu|dogrulama kodu|verification code|security code|güvenlik kodu|cvv|cvc|card.?num|kart.?n|iban|\bpin\b)/i;

// innerText of a textarea is its content, so form fields contribute no text at all.
function ownText(el) {
  return /^(input|textarea|select)$/i.test(el.tagName) ? '' : el.innerText;
}

function clip(text, limit = TEXT_LIMIT) {
  const t = (text || '').replace(/\s+/g, ' ').trim();
  return t.length > limit ? t.slice(0, limit) + '…' : t;
}

// password, OTP and card fields: their value, and their pixels, must never reach the model.
function isSensitiveField(el) {
  const tag = el.tagName.toLowerCase();
  if (tag !== 'input' && tag !== 'textarea') return false;
  if ((el.getAttribute('type') || '').toLowerCase() === 'password') return true;
  if (SENSITIVE_AUTOCOMPLETE.test(el.getAttribute('autocomplete') || '')) return true;
  const hints = ['name', 'id', 'aria-label', 'placeholder'].map((a) => el.getAttribute(a) || '');
  if (el.labels) for (const l of el.labels) hints.push(l.innerText || '');
  return hints.some((h) => SENSITIVE_HINT.test(h));
}

function idrefText(el, attr) {
  const ids = (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean);
  return clip(ids.map((id) => el.ownerDocument.getElementById(id)?.innerText || '').join(' '));
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
    labels: el.labels ? Array.from(el.labels, (l) => clip(l.innerText)) : [],
    text: sensitive ? '' : clip(ownText(el)),
    images: Array.from(el.querySelectorAll('img, svg'), (i) => clip(i.getAttribute('alt') || i.getAttribute('aria-label') || i.querySelector?.('title')?.textContent || '', 80)).filter(Boolean),
    nearby: {
      before: clip(el.previousElementSibling?.innerText, 150),
      after: clip(el.nextElementSibling?.innerText, 150),
      parent: clip(el.parentElement?.innerText),
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
      (el.labels ? Array.from(el.labels, (l) => l.innerText).join(' ') : '') ||
      ownText(el) ||
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
    const r = el.getBoundingClientRect();
    return r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  };
  const visible = (sel) => Array.from(doc.querySelectorAll(sel)).filter(isVisible);
  const controls = visible(CONTROLS).map((el) => {
    const name = accessibleName(el);
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      type: el.getAttribute('type'),
      name,
      unlabeled: !name,
      inViewport: inView(el),
      sensitive: isSensitiveField(el),
    };
  });
  controls.sort((a, b) => b.inViewport - a.inViewport); // stable: document order within each group
  const main = doc.querySelector('main, [role=main]') || doc.body;
  return {
    headings: visible('h1, h2, h3, h4, h5, h6, [role=heading]').map((el) => ({
      level: Number(el.getAttribute('aria-level') || el.tagName.slice(1)) || null,
      text: clip(el.innerText, 120),
    })),
    landmarks: visible(LANDMARKS).map((el) => ({
      role: el.getAttribute('role') || el.tagName.toLowerCase(),
      name: clip(el.getAttribute('aria-label') || idrefText(el, 'aria-labelledby'), 80),
    })),
    alerts: visible('[role=alert], [role=status], [aria-live]:not([aria-live=off])')
      .map((el) => clip(el.innerText, 200))
      .filter(Boolean),
    controls: controls.slice(0, OUTLINE_CONTROL_LIMIT),
    controlCount: controls.length,
    mainText: clip(main ? main.innerText : '', 1500),
  };
}

function sensitiveRects(elements) {
  const rects = [];
  for (const el of elements) {
    if (!isSensitiveField(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) rects.push([r.x, r.y, r.width, r.height]);
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

if (typeof module !== 'undefined') module.exports = { isSensitiveField, describeElement, pageOutline, sensitiveRects, cropBox };
