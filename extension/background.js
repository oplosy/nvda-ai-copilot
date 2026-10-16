// Relays coordinator requests (native messaging) to the content script of the active tab.

const HOST = 'com.nvda_ai_copilot.coordinator';
const RECONNECT_MS = 5000;

function connect() {
  const port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener(async (msg) => {
    let reply;
    try {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tab) throw new Error('no active tab');
      reply = await chrome.tabs.sendMessage(tab.id, msg, { frameId: 0 });
      if (!reply) throw new Error('content script did not answer (reload the page?)');
    } catch (e) {
      reply = { error: String(e && e.message ? e.message : e) };
    }
    port.postMessage({ ...reply, requestId: msg.requestId });
  });
  port.onDisconnect.addListener(() => {
    console.warn('native host disconnected:', chrome.runtime.lastError?.message);
    setTimeout(connect, RECONNECT_MS);
  });
}

// Registering onStartup makes Chrome wake the service worker at launch; the open port keeps it alive.
chrome.runtime.onStartup.addListener(() => {});
connect();
