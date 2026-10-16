# NVDA AI Copilot: maps the browse-mode navigator object to an extension element ID.
# NVDA objects are read on the main thread; coordinator calls run in a worker thread
# so speech and navigation never wait on the network.

import json
import os
import socket
import threading

import api
import core
import globalPluginHandler
import gui
import queueHandler
import ui
import wx
from logHandler import log
from NVDAObjects.IAccessible import IAccessible
from scriptHandler import script

SESSION_FILE = os.path.join(os.environ["LOCALAPPDATA"], "nvda-ai-copilot", "session.json")
REQUEST_TIMEOUT_S = 5
EXPLAIN_TIMEOUT_S = 45  # covers the model call (coordinator client timeout is 30 s + one retry)
# The class attribute showed up 15-31 ms after the DOM change in Chrome 155; poll fast, give up after 0.5 s.
MARKER_POLL_MS = 25
MARKER_POLL_TRIES = 20
# shortcut: fixed delay so the reason is spoken after NVDA announces the newly focused element; tune from testing.
FOUND_SPEAK_DELAY_MS = 600


def _navContext(obj):
	attrs = obj.IA2Attributes
	ti = obj.treeInterceptor
	root = ti.rootNVDAObject if ti else None
	loc = obj.location
	rootLoc = root.location if root else None
	return {
		"tag": attrs.get("tag"),
		"htmlId": attrs.get("id"),
		"classes": attrs.get("class"),
		"screenRect": list(loc) if loc else None,
		# The document root stays at the viewport origin when scrolled (measured, docs/spike-dom-mapping.md).
		"viewportOrigin": list(rootLoc[:2]) if rootLoc else None,
	}


def _request(msg, timeout):
	with open(SESSION_FILE, encoding="utf-8") as f:
		session = json.load(f)
	with socket.create_connection(("127.0.0.1", session["port"]), timeout=timeout) as s:
		s.sendall((json.dumps({**msg, "token": session["token"]}) + "\n").encode("utf-8"))
		line = s.makefile(encoding="utf-8").readline()
	if not line:
		raise ValueError("coordinator closed the connection")
	return json.loads(line)


def _onMain(func, *args):
	queueHandler.queueFunction(queueHandler.eventQueue, func, *args)


def _call(msg, timeout=REQUEST_TIMEOUT_S):
	"""Worker-thread request; speaks the failure and returns None on error."""
	try:
		reply = _request(msg, timeout)
	except TimeoutError:
		log.warning(f"nvdaAiCopilot: {msg['type']} timed out")
		_onMain(ui.message, "Copilot: yanıt zaman aşımına uğradı")
		return None
	except (OSError, ValueError, KeyError) as e:
		log.warning(f"nvdaAiCopilot: coordinator request failed: {e}")
		_onMain(ui.message, "Copilot: koordinatöre ulaşılamadı. Chrome ve eklenti açık mı?")
		return None
	log.info(f"nvdaAiCopilot: {msg['type']} nonce={msg.get('nonce')} -> {reply}")
	return reply


def _explainMatched(located):
	_askModel({"type": "explain", "elementId": located["elementId"]})


def _askModel(msg):
	"""Worker thread: asks the coordinator for model output and speaks it."""
	_onMain(ui.message, "Copilot: AI'ya soruluyor")
	reply = _call(msg, EXPLAIN_TIMEOUT_S)
	if reply is None:
		return
	if reply.get("status") == "explained":
		# AI output is always marked, so it is never mistaken for what the page exposes.
		_onMain(ui.message, f"AI yorumu: {reply['text']}")
	else:
		_onMain(ui.message, _describe(reply))


def _describe(reply):
	status = reply.get("status")
	if status == "matched":
		return f"Copilot: {reply['elementId']}, {reply.get('tag')}, {reply.get('method')} ile eşlendi"
	if status == "ambiguous":
		return f"Copilot: kesin eşlenemedi, {len(reply.get('candidates') or [])} aday"
	if status == "none":
		return "Copilot: eşleşen öğe bulunamadı"
	return f"Copilot hatası: {reply.get('message')}"


def _find(query):
	"""Worker thread: the coordinator picks an element, the extension focuses it, NVDA follows focus."""
	_onMain(ui.message, "Copilot: aranıyor")
	reply = _call({"type": "find", "query": query}, EXPLAIN_TIMEOUT_S)
	if reply is None:
		return
	status = reply.get("status")
	if status == "found":
		text = f"AI yorumu: {reply['text']}"
		if not reply.get("focused"):
			text += " Odak taşınamadı."
		_onMain(core.callLater, FOUND_SPEAK_DELAY_MS, ui.message, text)
	elif status == "none":
		_onMain(ui.message, f"AI yorumu: {reply['text']}")
	else:
		_onMain(ui.message, _describe(reply))


def _askQuery():
	"""Main (wx) thread: ask what to find, then search in a worker."""
	gui.mainFrame.prePopup()
	dlg = wx.TextEntryDialog(gui.mainFrame, "Sayfada ne arıyorsun?", "NVDA AI Copilot")
	try:
		ok = dlg.ShowModal() == wx.ID_OK
		query = dlg.GetValue().strip()
	finally:
		dlg.Destroy()
		gui.mainFrame.postPopup()
	if ok and query:
		threading.Thread(target=_find, args=(query[:300],), daemon=True).start()


def _webNavigator():
	obj = api.getNavigatorObject()
	if not isinstance(obj, IAccessible) or obj.appModule.appName != "chrome":
		ui.message("Copilot: navigator nesnesi bir Chrome web öğesi değil")
		return None
	return obj


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# shortcut: NVDA+Alt+Shift gestures until the add-on is packaged and the final shortcuts are chosen.
	@script(description="NVDA AI Copilot: explain the navigator object with AI", gesture="kb:NVDA+alt+shift+e")
	def script_explain(self, gesture):
		obj = _webNavigator()
		if obj:
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, _explainMatched)

	@script(description="NVDA AI Copilot: summarize the current web page with AI", gesture="kb:NVDA+alt+shift+p")
	def script_summarize(self, gesture):
		if api.getFocusObject().appModule.appName != "chrome":
			ui.message("Copilot: odak Chrome'da değil")
			return
		threading.Thread(target=_askModel, args=({"type": "summarize"},), daemon=True).start()

	@script(description="NVDA AI Copilot: find something on the web page with AI and move there", gesture="kb:NVDA+alt+shift+f")
	def script_find(self, gesture):
		if api.getFocusObject().appModule.appName != "chrome":
			ui.message("Copilot: odak Chrome'da değil")
			return
		wx.CallAfter(_askQuery)

	@script(description="NVDA AI Copilot: locate navigator object in the page (debug)", gesture="kb:NVDA+alt+shift+l")
	def script_locate(self, gesture):
		obj = _webNavigator()
		if obj:
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, None)

	def _locate(self, obj, msg, onMatched):
		"""onMatched(reply) runs on the worker thread once the element is grounded."""

		def worker():
			reply = _call(msg)
			if reply is None:
				return
			if reply.get("status") == "ambiguous" and reply.get("nonce") and not msg.get("nonce"):
				_onMain(self._pollMarker, obj, reply["nonce"], MARKER_POLL_TRIES, onMatched)
			elif reply.get("status") == "matched" and onMatched:
				onMatched(reply)
			else:
				_onMain(ui.message, _describe(reply))

		threading.Thread(target=worker, daemon=True).start()

	def _pollMarker(self, obj, nonce, triesLeft, onMatched):
		# Chromium updates the IA2 class attribute asynchronously after the DOM change.
		nav = _navContext(obj)
		if f"nvai-{nonce}-" not in (nav["classes"] or "") and triesLeft > 1:
			core.callLater(MARKER_POLL_MS, self._pollMarker, obj, nonce, triesLeft - 1, onMatched)
			return
		self._locate(obj, {"type": "locate", "nav": nav, "nonce": nonce}, onMatched)
