// Structured, value-free description of one element for the coordinator, plus the
// geometry for a masked screenshot crop. Field values are never read.

const TEXT_LIMIT = 300;
const SENSITIVE_AUTOCOMPLETE = /\b(cc-|one-time-code|current-password|new-password)/i;
const SENSITIVE_HINT =
  /(passw|parola|şifre|sifre|otp|one.?time|tek kullanımlık|doğrulama kodu|dogrulama kodu|verification code|security code|güvenlik kodu|cvv|cvc|card.?num|kart.?n|iban|\bpin\b)/i;

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
    text: sensitive ? '' : clip(el.innerText),
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

if (typeof module !== 'undefined') module.exports = { isSensitiveField, describeElement, sensitiveRects, cropBox };
