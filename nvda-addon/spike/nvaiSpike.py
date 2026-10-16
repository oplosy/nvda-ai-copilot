# Spike: map NVDA's browse-mode navigator object to a Chrome DOM element.
# Throwaway code. Load via the NVDA developer scratchpad (see docs/spike-dom-mapping.md).

import ctypes
import json
from ctypes import wintypes

import api
import globalPluginHandler
import textInfos
import ui
from logHandler import log
from NVDAObjects.IAccessible import IAccessible
from scriptHandler import script

TAG = "NVAI-SPIKE"

# Runs in the page's DevTools console. N is filled in from Python.
JS_TEMPLATE = r"""(() => {
const N = %s;
const dpr = devicePixelRatio;
const desc = e => !e ? null : e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') +
  (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\s+/).join('.') : '');
const iou = (a, b) => {
  const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  const i = w > 0 && h > 0 ? w * h : 0;
  const u = a.width * a.height + b.width * b.height - i;
  return u > 0 ? i / u : 0;
};
const all = [...document.querySelectorAll('body, body *')];
const out = {url: location.href, dpr, inIframeHint: 'top document only'};
for (const [k, o] of Object.entries(N.origins)) {
  if (!o || !N.screen) continue;
  const r = new DOMRect((N.screen[0] - o[0]) / dpr, (N.screen[1] - o[1]) / dpr, N.screen[2] / dpr, N.screen[3] / dpr);
  const ranked = all.map(e => ({e, s: iou(r, e.getBoundingClientRect())})).filter(c => c.s > 0).sort((a, b) => b.s - a.s);
  out['rect_' + k] = {
    cssRect: [r.x, r.y, r.width, r.height].map(v => Math.round(v)),
    ambiguous_iou_gt_0_9: ranked.filter(c => c.s > 0.9).length,
    top: ranked.slice(0, 4).map(c => ({el: desc(c.e), iou: +c.s.toFixed(3), tagMatch: c.e.tagName.toLowerCase() === N.tag})),
  };
}
if (N.id) {
  const els = document.querySelectorAll('#' + CSS.escape(N.id));
  out.byId = {count: els.length, el: desc(els[0]), tagMatch: !!els[0] && els[0].tagName.toLowerCase() === N.tag};
}
const marker = (N.cls || '').split(/\s+/).find(c => c.startsWith('nvai-'));
if (marker) out.byMarker = desc(document.querySelector('.' + CSS.escape(marker)));
const sel = getSelection();
if (sel.rangeCount) {
  let n = sel.getRangeAt(0).commonAncestorContainer;
  if (n.nodeType !== 1) n = n.parentElement;
  out.bySelection = {el: desc(n), text: sel.toString().slice(0, 80)};
}
console.log(JSON.stringify(out, null, 2));
return out;
})()"""


def _clientOrigin(hwnd):
	pt = wintypes.POINT(0, 0)
	if hwnd and ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt)):
		return [pt.x, pt.y]
	return None


def _loc(obj):
	loc = obj.location if obj else None
	return list(loc) if loc else None


def _brief(obj):
	attrs = getattr(obj, "IA2Attributes", {}) or {}
	return {
		"role": obj.role.name,
		"name": (obj.name or "")[:60],
		"tag": attrs.get("tag"),
		"id": attrs.get("id"),
		"class": attrs.get("class"),
		"loc": _loc(obj),
	}


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	@script(description="NVAI spike: log navigator object mapping data", gesture="kb:NVDA+alt+shift+i")
	def script_inspect(self, gesture):
		obj = api.getNavigatorObject()
		if not isinstance(obj, IAccessible):
			ui.message(f"Spike: navigator IAccessible değil ({type(obj).__name__})")
			log.info(f"{TAG} not IAccessible: {type(obj).__mro__}")
			return
		attrs = obj.IA2Attributes
		ti = obj.treeInterceptor
		root = ti.rootNVDAObject if ti else None
		states = sorted(s.name for s in obj.states)
		chain = []
		p = obj.parent
		while p and len(chain) < 12 and isinstance(p, IAccessible):
			chain.append(_brief(p))
			if root and p == root:
				break
			p = p.parent
		data = {
			"app": obj.appModule.appName,
			"nvdaClasses": [c.__name__ for c in type(obj).__mro__[:6]],
			"windowClassName": obj.windowClassName,
			"windowHandle": obj.windowHandle,
			"role": obj.role.name,
			"name": obj.name,
			"states": states,
			"IA2UniqueID": getattr(obj, "IA2UniqueID", None),
			"IA2Attributes": attrs,
			"location": _loc(obj),
			"docRootLocation": _loc(root),
			"renderWidgetClientOrigin": _clientOrigin(obj.windowHandle),
			"passThrough": getattr(ti, "passThrough", None),
			"ancestors": chain,
		}
		log.info(f"{TAG} inspect:\n{json.dumps(data, ensure_ascii=False, indent=1, default=str)}")
		docLoc = data["docRootLocation"]
		n = {
			"screen": data["location"],
			"origins": {"docRoot": docLoc[:2] if docLoc else None, "renderWidget": data["renderWidgetClientOrigin"]},
			"id": attrs.get("id"),
			"cls": attrs.get("class"),
			"tag": attrs.get("tag"),
		}
		js = JS_TEMPLATE % json.dumps(n, ensure_ascii=False)
		log.info(f"{TAG} js:\n{js}")
		api.copyToClip(js)
		ui.message(f"Spike: {attrs.get('tag')} id {attrs.get('id') or 'yok'}. Log yazıldı, JS panoda.")

	@script(description="NVAI spike: set browser selection to navigator object", gesture="kb:NVDA+alt+shift+s")
	def script_selectNavigator(self, gesture):
		obj = api.getNavigatorObject()
		try:
			info = obj.makeTextInfo(textInfos.POSITION_ALL)
			log.info(f"{TAG} select: textInfo={type(info).__name__} text={info.text[:80]!r}")
			info.updateSelection()
		except Exception:
			log.exception(f"{TAG} select failed")
			ui.message("Spike: seçim ayarlanamadı, loga bak")
			return
		ui.message("Spike: tarayıcı seçimi navigator nesnesine ayarlandı")
