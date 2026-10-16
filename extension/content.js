// Answers coordinator requests in the top frame. Uses helpers from grounding.js and context.js.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const all = document.body ? document.body.querySelectorAll('*') : [];
  if (msg.type === 'snapshot') {
    sendResponse({ url: location.href, dpr: devicePixelRatio, elements: snapshot(all) });
  } else if (msg.type === 'mark') {
    markElements(all, new Set(msg.ids), msg.nonce);
    sendResponse({ ok: true });
  } else if (msg.type === 'clear') {
    clearMarkers(all, msg.nonce);
    sendResponse({ ok: true });
  } else if (msg.type === 'context') {
    const el = elementById(msg.elementId);
    if (!el) {
      sendResponse({ error: 'element is no longer in the page' });
      return;
    }
    const r = el.getBoundingClientRect();
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      element: describeElement(el),
      rect: [r.x, r.y, r.width, r.height],
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else {
    sendResponse({ error: `unknown request type: ${msg.type}` });
  }
});
