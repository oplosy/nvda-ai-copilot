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
from gui import guiHelper, settingsDialogs
from logHandler import log
from NVDAObjects.IAccessible import IAccessible
from scriptHandler import script

from . import secret  # copied from coordinator/secret.py by build.py

SESSION_FILE = os.path.join(os.environ["LOCALAPPDATA"], "nvda-ai-copilot", "session.json")
REQUEST_TIMEOUT_S = 5
EXPLAIN_TIMEOUT_S = 45  # covers the model call (coordinator: 20 s timeout, one retry, ~41 s worst case)
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
		_onMain(ui.message, "Copilot: koordinatöre ulaşılamadı. Tarayıcı ve eklenti açık mı?")
		return None
	# The NVDA log gets pasted into bug reports, so AI text about the page stays out of it.
	logged = {k: v for k, v in reply.items() if k != "text"}
	log.info(f"nvdaAiCopilot: {msg['type']} nonce={msg.get('nonce')} -> {logged}")
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
	if status == "info":
		return f"Copilot: {reply.get('text')}"
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


def _askText(prompt, worker):
	"""Main (wx) thread: ask for a line of text, then run worker(text) in a worker thread."""
	gui.mainFrame.prePopup()
	dlg = wx.TextEntryDialog(gui.mainFrame, prompt, "NVDA AI Copilot")
	try:
		ok = dlg.ShowModal() == wx.ID_OK
		text = dlg.GetValue().strip()
	finally:
		dlg.Destroy()
		gui.mainFrame.postPopup()
	if ok and text:
		threading.Thread(target=worker, args=(text[:300],), daemon=True).start()


def _sections():
	"""Worker thread: the model names the page's parts; the person picks one and focus moves there."""
	_onMain(ui.message, "Copilot: bölümler çıkarılıyor")
	reply = _call({"type": "sections"}, EXPLAIN_TIMEOUT_S)
	if reply is None:
		return
	if reply.get("status") == "sections":
		wx.CallAfter(_chooseSection, reply["sections"])
	else:
		_onMain(ui.message, _describe(reply))


def _chooseSection(sections):
	"""Main (wx) thread: list the AI's sections; the list itself is marked as AI output."""
	gui.mainFrame.prePopup()
	dlg = wx.SingleChoiceDialog(
		gui.mainFrame,
		"AI yorumu: sayfanın bölümleri. Seçtiğin bölüme odak taşınır.",
		"NVDA AI Copilot",
		[s["title"] for s in sections],
	)
	try:
		ok = dlg.ShowModal() == wx.ID_OK
		index = dlg.GetSelection()
	finally:
		dlg.Destroy()
		gui.mainFrame.postPopup()
	if ok and index >= 0:
		threading.Thread(target=_focusSection, args=(sections[index]["elementId"],), daemon=True).start()


def _focusSection(elementId):
	reply = _call({"type": "focus", "elementId": elementId})
	if reply is None:
		return
	if reply.get("status") != "focused":
		_onMain(ui.message, _describe(reply))
	elif not reply.get("focused"):
		_onMain(ui.message, "Copilot: odak taşınamadı")


# Chromium browsers the extension runs in.
BROWSERS = ("chrome", "msedge")


def _webNavigator():
	obj = api.getNavigatorObject()
	if not isinstance(obj, IAccessible) or obj.appModule.appName not in BROWSERS:
		ui.message("Copilot: navigator nesnesi bir Chrome veya Edge web öğesi değil")
		return None
	return obj


def _browserFocused():
	if api.getFocusObject().appModule.appName in BROWSERS:
		return True
	ui.message("Copilot: odak Chrome veya Edge'de değil")
	return False


class CopilotSettingsPanel(settingsDialogs.SettingsPanel):
	"""NVDA settings category for the Anthropic API key; the key is stored DPAPI-encrypted."""

	title = "NVDA AI Copilot"

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		label = "Anthropic API anahtarı"
		if secret.has_key():
			label += " (kayıtlı bir anahtar var; değiştirmek için yenisini yapıştır)"
		self.keyEdit = helper.addLabeledControl(label, wx.TextCtrl, style=wx.TE_PASSWORD)
		self.deleteCheck = helper.addItem(wx.CheckBox(self, label="Kayıtlı anahtarı sil"))

	def isValid(self):
		key = self.keyEdit.GetValue().strip()
		if key and not secret.valid_key(key):
			gui.messageBox(
				"API anahtarı geçersiz görünüyor: boşluk veya Türkçe karakter içermemeli.",
				"NVDA AI Copilot",
				wx.OK | wx.ICON_ERROR,
				self,
			)
			return False
		return super().isValid()

	def onSave(self):
		key = self.keyEdit.GetValue().strip()
		try:
			if key:
				secret.save_key(key)
			elif self.deleteCheck.IsChecked():
				secret.delete_key()
		except OSError as e:
			log.error(f"nvdaAiCopilot: API key could not be saved: {e}")
			gui.messageBox("API anahtarı kaydedilemedi, NVDA loguna bak.", "NVDA AI Copilot", wx.OK | wx.ICON_ERROR)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		settingsDialogs.NVDASettingsDialog.categoryClasses.append(CopilotSettingsPanel)

	def terminate(self):
		settingsDialogs.NVDASettingsDialog.categoryClasses.remove(CopilotSettingsPanel)
		super().terminate()

	# shortcut: NVDA+Alt+Shift gestures until the add-on is packaged and the final shortcuts are chosen.
	@script(description="NVDA AI Copilot: explain the navigator object with AI", gesture="kb:NVDA+alt+shift+e")
	def script_explain(self, gesture):
		obj = _webNavigator()
		if obj:
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, _explainMatched)

	@script(description="NVDA AI Copilot: explain the form around the navigator object with AI", gesture="kb:NVDA+alt+shift+r")
	def script_form(self, gesture):
		obj = _webNavigator()
		if obj:
			onMatched = lambda located: _askModel({"type": "form", "elementId": located["elementId"]})  # noqa: E731
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, onMatched)

	@script(description="NVDA AI Copilot: explain the table around the navigator object with AI", gesture="kb:NVDA+alt+shift+t")
	def script_table(self, gesture):
		obj = _webNavigator()
		if obj:
			onMatched = lambda located: _askModel({"type": "table", "elementId": located["elementId"]})  # noqa: E731
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, onMatched)

	@script(description="NVDA AI Copilot: summarize the current web page with AI", gesture="kb:NVDA+alt+shift+p")
	def script_summarize(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_askModel, args=({"type": "summarize"},), daemon=True).start()

	@script(description="NVDA AI Copilot: find something on the web page with AI and move there", gesture="kb:NVDA+alt+shift+f")
	def script_find(self, gesture):
		if not _browserFocused():
			return
		wx.CallAfter(_askText, "Sayfada ne arıyorsun?", _find)

	@script(description="NVDA AI Copilot: say what changed on the page since the last click or key press", gesture="kb:NVDA+alt+shift+c")
	def script_changes(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_askModel, args=({"type": "changes"},), daemon=True).start()

	@script(description="NVDA AI Copilot: list the page's parts found by AI and move to one", gesture="kb:NVDA+alt+shift+b")
	def script_sections(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_sections, daemon=True).start()

	@script(description="NVDA AI Copilot: ask a follow-up question about the last AI answer", gesture="kb:NVDA+alt+shift+q")
	def script_followup(self, gesture):
		wx.CallAfter(
			_askText,
			"Son AI cevabı hakkında ne sormak istiyorsun?",
			lambda question: _askModel({"type": "followup", "query": question}),
		)

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
