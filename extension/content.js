// Answers coordinator requests in the top frame. Uses helpers from grounding.js.

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
  } else {
    sendResponse({ error: `unknown request type: ${msg.type}` });
  }
});
