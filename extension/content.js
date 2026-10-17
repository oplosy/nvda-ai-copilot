// Answers coordinator requests in the top frame. Uses helpers from grounding.js, context.js and changes.js.

chrome.runtime.sendMessage({ type: 'hello' }).catch(() => {}); // wakes the worker; no reply expected

const changeTracker = createChangeTracker(document);

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const all = allElements(document);
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
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      element: describeElement(el),
      url: location.origin + location.pathname, // report header only; never sent to the model
      rect: topRect(el),
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else if (msg.type === 'focus') {
    const el = elementById(msg.elementId);
    if (!el) {
      sendResponse({ error: 'element is no longer in the page' });
      return;
    }
    sendResponse({ focused: focusElement(el) });
  } else if (msg.type === 'form') {
    const el = elementById(msg.elementId);
    if (!el) {
      sendResponse({ error: 'element is no longer in the page' });
      return;
    }
    const form = formContext(el);
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      form,
      rect: form.rect,
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else if (msg.type === 'table') {
    const el = elementById(msg.elementId);
    if (!el) {
      sendResponse({ error: 'element is no longer in the page' });
      return;
    }
    const table = tableContext(el);
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      table,
      rect: table ? table.rect : [0, 0, 0, 0],
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else if (msg.type === 'chart') {
    const el = elementById(msg.elementId);
    if (!el) {
      sendResponse({ error: 'element is no longer in the page' });
      return;
    }
    const chart = chartContext(el);
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      chart,
      rect: chart ? chart.rect : [0, 0, 0, 0],
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else if (msg.type === 'changes') {
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      changes: { ...changeTracker.report(), alerts: pageAlerts(document) },
      rect: [0, 0, innerWidth, innerHeight],
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else if (msg.type === 'sections') {
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      sections: pageSections(document),
      rect: [0, 0, innerWidth, innerHeight],
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else if (msg.type === 'outline') {
    sendResponse({
      page: { origin: location.origin, title: clip(document.title, 150) },
      outline: pageOutline(document),
      rect: [0, 0, innerWidth, innerHeight], // screenshot the whole viewport
      viewport: [innerWidth, innerHeight],
      sensitiveRects: sensitiveRects(all),
    });
  } else {
    sendResponse({ error: `unknown request type: ${msg.type}` });
  }
});
