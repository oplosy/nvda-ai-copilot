// Relays coordinator requests (native messaging) to the content script of the active tab.

importScripts('context.js');

const HOST = 'com.nvda_ai_copilot.coordinator';
const RECONNECT_MS = 5000;
const MAX_IMAGE_EDGE = 1568; // larger images are downscaled by the API anyway

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

// Screenshot of the area around the element, with sensitive fields painted black.
async function maskedCrop(windowId, ctx) {
  if (!cropBox(ctx.rect, ctx.viewport, 1)) return null;
  const dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: 'png' });
  const bitmap = await createImageBitmap(await (await fetch(dataUrl)).blob());
  const scale = bitmap.width / ctx.viewport[0];
  const [bx, by, bw, bh] = cropBox(ctx.rect, ctx.viewport, scale);
  const out = Math.min(1, MAX_IMAGE_EDGE / Math.max(bw, bh));
  const canvas = new OffscreenCanvas(Math.round(bw * out), Math.round(bh * out));
  const g = canvas.getContext('2d');
  g.scale(out, out);
  g.drawImage(bitmap, bx, by, bw, bh, 0, 0, bw, bh);
  g.fillStyle = '#000';
  for (const [x, y, w, h] of ctx.sensitiveRects) g.fillRect(x * scale - bx, y * scale - by, w * scale, h * scale);
  const blob = await canvas.convertToBlob({ type: 'image/png' });
  return toBase64(await blob.arrayBuffer());
}

async function handle(msg) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) throw new Error('no active tab');
  const reply = await chrome.tabs.sendMessage(tab.id, msg, { frameId: 0 });
  if (!reply) throw new Error('content script did not answer (reload the page?)');
  if (msg.type === 'context' && !reply.error) {
    try {
      reply.screenshot = await maskedCrop(tab.windowId, reply);
    } catch (e) {
      reply.screenshot = null;
      reply.screenshotError = String(e && e.message ? e.message : e);
    }
  }
  return reply;
}

function connect() {
  const port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener(async (msg) => {
    let reply;
    try {
      reply = await handle(msg);
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
