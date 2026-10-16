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
import queueHandler
import ui
from logHandler import log
from NVDAObjects.IAccessible import IAccessible
from scriptHandler import script

SESSION_FILE = os.path.join(os.environ["LOCALAPPDATA"], "nvda-ai-copilot", "session.json")
REQUEST_TIMEOUT_S = 5
MARKER_POLL_MS = 100
MARKER_POLL_TRIES = 10


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
		# shortcut: viewport origin = document root position, unconfirmed until the spike log (docs/spike-dom-mapping.md).
		"viewportOrigin": list(rootLoc[:2]) if rootLoc else None,
	}


def _request(msg):
	with open(SESSION_FILE, encoding="utf-8") as f:
		session = json.load(f)
	with socket.create_connection(("127.0.0.1", session["port"]), timeout=REQUEST_TIMEOUT_S) as s:
		s.sendall((json.dumps({**msg, "token": session["token"]}) + "\n").encode("utf-8"))
		line = s.makefile(encoding="utf-8").readline()
	if not line:
		raise ValueError("coordinator closed the connection")
	return json.loads(line)


def _onMain(func, *args):
	queueHandler.queueFunction(queueHandler.eventQueue, func, *args)


def _describe(reply):
	status = reply.get("status")
	if status == "matched":
		return f"Copilot: {reply['elementId']}, {reply.get('tag')}, {reply.get('method')} ile eşlendi"
	if status == "ambiguous":
		return f"Copilot: kesin eşlenemedi, {len(reply.get('candidates') or [])} aday"
	if status == "none":
		return "Copilot: eşleşen öğe bulunamadı"
	return f"Copilot hatası: {reply.get('message')}"


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# shortcut: debug gesture for grounding only; the user-facing shortcut comes with the explain feature.
	@script(description="NVDA AI Copilot: locate navigator object in the page", gesture="kb:NVDA+alt+shift+l")
	def script_locate(self, gesture):
		obj = api.getNavigatorObject()
		if not isinstance(obj, IAccessible) or obj.appModule.appName != "chrome":
			ui.message("Copilot: navigator nesnesi bir Chrome web öğesi değil")
			return
		self._send(obj, {"type": "locate", "nav": _navContext(obj)})

	def _send(self, obj, msg):
		def worker():
			try:
				reply = _request(msg)
			except (OSError, ValueError, KeyError) as e:
				log.warning(f"nvdaAiCopilot: coordinator request failed: {e}")
				_onMain(ui.message, "Copilot: koordinatöre ulaşılamadı. Chrome ve eklenti açık mı?")
				return
			log.info(f"nvdaAiCopilot: {msg['type']} nonce={msg.get('nonce')} -> {reply}")
			if reply.get("status") == "ambiguous" and reply.get("nonce") and not msg.get("nonce"):
				_onMain(self._pollMarker, obj, reply["nonce"], MARKER_POLL_TRIES)
			else:
				_onMain(ui.message, _describe(reply))

		threading.Thread(target=worker, daemon=True).start()

	def _pollMarker(self, obj, nonce, triesLeft):
		# Chromium updates the IA2 class attribute asynchronously after the DOM change.
		nav = _navContext(obj)
		if f"nvai-{nonce}-" not in (nav["classes"] or "") and triesLeft > 1:
			core.callLater(MARKER_POLL_MS, self._pollMarker, obj, nonce, triesLeft - 1)
			return
		self._send(obj, {"type": "locate", "nav": nav, "nonce": nonce})
