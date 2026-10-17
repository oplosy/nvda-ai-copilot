# NVDA AI Copilot: maps the browse-mode navigator object to an extension element ID.
# NVDA objects are read on the main thread; coordinator calls run in a worker thread
# so speech and navigation never wait on the network.

import json
import os
import re
import socket
import threading
from urllib.parse import urlsplit

import addonHandler
import api
import config
import core
import globalPluginHandler
import gui
import languageHandler
import queueHandler
import ui
import wx
from gui import guiHelper, settingsDialogs
from logHandler import log
from NVDAObjects.IAccessible import IAccessible
from scriptHandler import script

from . import secret  # copied from coordinator/secret.py by build.py

addonHandler.initTranslation()

SESSION_FILE = os.path.join(os.environ["LOCALAPPDATA"], "nvda-ai-copilot", "session.json")
REQUEST_TIMEOUT_S = 5
EXPLAIN_TIMEOUT_S = 45  # covers the model call (coordinator: 20 s timeout, one retry, ~41 s worst case)
# The class attribute showed up 15-31 ms after the DOM change in Chrome 155; poll fast, give up after 0.5 s.
MARKER_POLL_MS = 25
MARKER_POLL_TRIES = 20
# shortcut: fixed delay so the reason is spoken after NVDA announces the newly focused element; tune from testing.
FOUND_SPEAK_DELAY_MS = 600
# Chromium browsers the extension runs in.
BROWSERS = ("chrome", "msedge")

CONF_SECTION = "nvdaAiCopilot"
config.conf.spec[CONF_SECTION] = {
	"sendScreenshots": "boolean(default=True)",
	"blockedSites": "string(default='')",  # host names separated by spaces
}


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


def _settings():
	"""Sent with every request; the coordinator enforces them before anything reaches the model."""
	conf = config.conf[CONF_SECTION]
	return {
		"screenshots": bool(conf["sendScreenshots"]),
		"blockedSites": conf["blockedSites"].split(),
		"language": languageHandler.getLanguage(),
	}


def _request(msg, timeout, onPartial=None):
	"""One JSON line per reply; "partial" lines carry finished sentences of an answer still being written."""
	with open(SESSION_FILE, encoding="utf-8") as f:
		session = json.load(f)
	with socket.create_connection(("127.0.0.1", session["port"]), timeout=timeout) as s:
		s.sendall((json.dumps({**msg, "settings": _settings(), "token": session["token"]}) + "\n").encode("utf-8"))
		for line in s.makefile(encoding="utf-8"):
			reply = json.loads(line)
			if reply.get("status") != "partial":
				return reply
			if onPartial:
				onPartial(reply["text"])
	raise ValueError("coordinator closed the connection")


def _onMain(func, *args):
	queueHandler.queueFunction(queueHandler.eventQueue, func, *args)


def _call(msg, timeout=REQUEST_TIMEOUT_S, onPartial=None):
	"""Worker-thread request; speaks the failure and returns None on error."""
	try:
		reply = _request(msg, timeout, onPartial)
	except TimeoutError:
		log.warning(f"nvdaAiCopilot: {msg['type']} timed out")
		# Translators: spoken when the coordinator did not answer in time.
		_onMain(ui.message, _("Copilot: the answer timed out"))
		return None
	except (OSError, ValueError, KeyError) as e:
		log.warning(f"nvdaAiCopilot: coordinator request failed: {e}")
		# Translators: spoken when the local coordinator service cannot be reached.
		_onMain(ui.message, _("Copilot: cannot reach the coordinator. Are the browser and the extension running?"))
		return None
	# The NVDA log gets pasted into bug reports, so AI text about the page stays out of it.
	logged = {k: v for k, v in reply.items() if k != "text"}
	log.info(f"nvdaAiCopilot: {msg['type']} nonce={msg.get('nonce')} -> {logged}")
	return reply


def _aiComment(text):
	# AI output is always marked, so it is never mistaken for what the page exposes.
	# Translators: prefix of every AI answer; keep it short and recognizable.
	return _("AI comment: {text}").format(text=text)


def _explainMatched(located):
	_askModel({"type": "explain", "elementId": located["elementId"]})


def _askModel(msg):
	"""Worker thread: asks the coordinator for model output and speaks it, sentence by sentence."""
	# Translators: spoken while waiting for an AI answer.
	_onMain(ui.message, _("Copilot: asking AI"))
	spoken = []

	def onPartial(text):
		_onMain(ui.message, text if spoken else _aiComment(text))
		spoken.append(text)

	reply = _call(msg, EXPLAIN_TIMEOUT_S, onPartial)
	if reply is None:
		return
	if reply.get("status") == "explained":
		if reply.get("saved"):
			# Translators: prefix of an AI comment the user saved earlier for this element.
			_onMain(ui.message, _("Saved AI comment: {text}").format(text=reply["text"]))
		elif not reply.get("streamed"):
			_onMain(ui.message, _aiComment(reply["text"]))
	else:
		_onMain(ui.message, _describe(reply))


def _messages():
	"""Translated text for the coordinator's info and error codes."""
	return {
		# Translators: spoken when the user turned Copilot off for the current site.
		"blocked": _("Copilot is turned off for this site in the NVDA settings"),
		"no_table": _("There is no table in or around this element"),
		"no_chart": _("There is no chart drawn as SVG in or around this element"),
		"no_guide": _("No guided task is running; start one first"),
		"guide_too_long": _("The guided task took too many steps and is stopped"),
		"no_label": _("Saving works on the last element explanation; explain an element first"),
		"label_unidentifiable": _("Nothing identifies this element on a later visit, so it cannot be saved"),
		"label_saved": _("Saved: this AI comment is spoken at once on later visits"),
		"label_deleted": _("The saved AI comment for this element is deleted"),
		"no_changes": _("Nothing visible changed since the last click or key press"),
		"no_sections": _("The page could not be split into parts"),
		"no_followup": _("A follow-up question is about the last AI answer; use an AI command first"),
		"key_missing": _("No Anthropic API key is set. Enter it in NVDA settings, NVDA AI Copilot category"),
		"key_invalid": _("The Anthropic API key is invalid. Check it in NVDA settings, NVDA AI Copilot category"),
		"key_unreadable": _("The saved API key could not be read. Enter it again in NVDA settings"),
		"rate_limit": _("The AI service is busy. Try again shortly"),
		"connection": _("Cannot reach the AI service. Check the internet connection"),
		"refusal": _("The AI declined to answer"),
		"empty": _("The AI gave an empty answer"),
		"bad_output": _("The AI gave an answer Copilot cannot use"),
	}


def _describe(reply):
	status = reply.get("status")
	if status == "matched":
		# Translators: debug command result: element ID, tag and how it was matched.
		return _("Copilot: {id}, {tag}, matched by {method}").format(
			id=reply["elementId"], tag=reply.get("tag"), method=reply.get("method")
		)
	if status == "ambiguous":
		return _("Copilot: no exact match, {count} candidates").format(count=len(reply.get("candidates") or []))
	if status == "none":
		return _("Copilot: no matching element found")
	text = _messages().get(reply.get("code")) or reply.get("text") or reply.get("message")
	if status == "info":
		return _("Copilot: {text}").format(text=text)
	# Translators: spoken when a command failed; the reason follows.
	return _("Copilot error: {text}").format(text=text)


def _report(located):
	"""Worker thread: the AI writes an issue report for the site; it goes to the clipboard, not to speech."""
	# Translators: spoken while the AI writes an accessibility report.
	_onMain(ui.message, _("Copilot: writing an accessibility report"))
	reply = _call({"type": "report", "elementId": located["elementId"]}, EXPLAIN_TIMEOUT_S)
	if reply is None:
		return
	if reply.get("status") == "report":
		_onMain(api.copyToClip, reply["text"])
		# Translators: spoken when the AI-written report is on the clipboard.
		_onMain(ui.message, _("Copilot: an AI-written accessibility report is on the clipboard. Paste it into an email or the site's feedback form."))
	else:
		_onMain(ui.message, _describe(reply))


def _guide(msg):
	"""Worker thread: speaks the next step; focus moves to its element and the person acts."""
	# Translators: spoken while the AI works out the next step of a guided task.
	_onMain(ui.message, _("Copilot: working out the next step"))
	reply = _call(msg, EXPLAIN_TIMEOUT_S)
	if reply is None:
		return
	if reply.get("status") != "guide":
		_onMain(ui.message, _describe(reply))
		return
	text = _aiComment(reply["text"])
	if reply.get("focused") is False:
		text += " " + _("Focus could not be moved.")
	if reply.get("done"):
		# Translators: spoken after the last step of a guided task.
		text += " " + _("The guided task is over.")
	else:
		# Translators: spoken after each step of a guided task.
		text += " " + _("When you have done it, ask for the next step.")
	# After NVDA announces the newly focused element, like find.
	_onMain(core.callLater, FOUND_SPEAK_DELAY_MS if reply.get("focused") else 0, ui.message, text)


def _toggleLabel():
	reply = _call({"type": "label"})
	if reply is not None:
		_onMain(ui.message, _describe(reply))


def _find(query):
	"""Worker thread: the coordinator picks an element, the extension focuses it, NVDA follows focus."""
	# Translators: spoken while the AI looks for what the user asked for.
	_onMain(ui.message, _("Copilot: searching"))
	reply = _call({"type": "find", "query": query}, EXPLAIN_TIMEOUT_S)
	if reply is None:
		return
	status = reply.get("status")
	if status == "found":
		text = _aiComment(reply["text"])
		if not reply.get("focused"):
			text += " " + _("Focus could not be moved.")
		_onMain(core.callLater, FOUND_SPEAK_DELAY_MS, ui.message, text)
	elif status == "none":
		_onMain(ui.message, _aiComment(reply["text"]))
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
	# Translators: spoken while the AI splits the page into parts.
	_onMain(ui.message, _("Copilot: finding the parts of the page"))
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
		# Translators: text of the dialog listing the page parts found by AI.
		_aiComment(_("the parts of the page. Focus moves to the part you choose.")),
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
		_onMain(ui.message, _("Copilot: focus could not be moved"))


def _webNavigator():
	obj = api.getNavigatorObject()
	if not isinstance(obj, IAccessible) or obj.appModule.appName not in BROWSERS:
		# Translators: spoken when a command needs a web element in Chrome or Edge.
		ui.message(_("Copilot: the navigator object is not a web element in Chrome or Edge"))
		return None
	return obj


def _browserFocused():
	if api.getFocusObject().appModule.appName in BROWSERS:
		return True
	ui.message(_("Copilot: the focus is not in Chrome or Edge"))
	return False


SITE = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*")


def _siteHost(entry):
	"""Same normalization as the coordinator's site_host: URL, *.host or host -> host, or None."""
	entry = entry.strip().lower()
	host = (urlsplit(entry if "://" in entry else "//" + entry).hostname or "").lstrip("*.")
	return host if SITE.fullmatch(host) else None


class CopilotSettingsPanel(settingsDialogs.SettingsPanel):
	"""API key (stored DPAPI-encrypted) and privacy settings."""

	title = "NVDA AI Copilot"

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: label of the API key field in NVDA settings.
		label = _("Anthropic API key")
		if secret.has_key():
			# Translators: added to the API key label when a key is already saved.
			label += " " + _("(a key is saved; paste a new one to replace it)")
		self.keyEdit = helper.addLabeledControl(label, wx.TextCtrl, style=wx.TE_PASSWORD)
		# Translators: checkbox that deletes the saved API key.
		self.deleteCheck = helper.addItem(wx.CheckBox(self, label=_("Delete the saved key")))
		conf = config.conf[CONF_SECTION]
		# Translators: checkbox in NVDA settings.
		self.screenshotsCheck = helper.addItem(
			wx.CheckBox(self, label=_("Send screenshots to the AI (sensitive fields are always blacked out)"))
		)
		self.screenshotsCheck.SetValue(conf["sendScreenshots"])
		# Translators: label of the list of sites where Copilot never sends anything.
		self.sitesEdit = helper.addLabeledControl(
			_("Sites where Copilot is off, separated by spaces or commas (for example mybank.com)"), wx.TextCtrl
		)
		self.sitesEdit.SetValue(", ".join(conf["blockedSites"].split()))

	def _siteEntries(self):
		return [s for s in re.split(r"[\s,;]+", self.sitesEdit.GetValue()) if s]

	def isValid(self):
		key = self.keyEdit.GetValue().strip()
		if key and not secret.valid_key(key):
			# Translators: error when the pasted API key has spaces or non-ASCII characters.
			gui.messageBox(_("The API key looks invalid: it must not contain spaces or special characters."), "NVDA AI Copilot", wx.OK | wx.ICON_ERROR, self)
			return False
		bad = [s for s in self._siteEntries() if not _siteHost(s)]
		if bad:
			# Translators: error listing site entries that are not host names.
			gui.messageBox(_("These are not site names: {sites}").format(sites=", ".join(bad)), "NVDA AI Copilot", wx.OK | wx.ICON_ERROR, self)
			return False
		return super().isValid()

	def onSave(self):
		conf = config.conf[CONF_SECTION]
		conf["sendScreenshots"] = self.screenshotsCheck.IsChecked()
		conf["blockedSites"] = " ".join(dict.fromkeys(_siteHost(s) for s in self._siteEntries()))
		key = self.keyEdit.GetValue().strip()
		try:
			if key:
				secret.save_key(key)
			elif self.deleteCheck.IsChecked():
				secret.delete_key()
		except OSError as e:
			log.error(f"nvdaAiCopilot: API key could not be saved: {e}")
			# Translators: error when the API key could not be written.
			gui.messageBox(_("The API key could not be saved; see the NVDA log."), "NVDA AI Copilot", wx.OK | wx.ICON_ERROR)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: category of this add-on's commands in the Input gestures dialog.
	scriptCategory = _("NVDA AI Copilot")

	def __init__(self):
		super().__init__()
		settingsDialogs.NVDASettingsDialog.categoryClasses.append(CopilotSettingsPanel)

	def terminate(self):
		settingsDialogs.NVDASettingsDialog.categoryClasses.remove(CopilotSettingsPanel)
		super().terminate()

	# Translators: input gesture description.
	@script(description=_("Explains the navigator object with AI"), gesture="kb:NVDA+alt+shift+e")
	def script_explain(self, gesture):
		obj = _webNavigator()
		if obj:
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, _explainMatched)

	# Translators: input gesture description.
	@script(description=_("Explains the form around the navigator object with AI"), gesture="kb:NVDA+alt+shift+r")
	def script_form(self, gesture):
		obj = _webNavigator()
		if obj:
			onMatched = lambda located: _askModel({"type": "form", "elementId": located["elementId"]})  # noqa: E731
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, onMatched)

	# Translators: input gesture description.
	@script(description=_("Explains the table around the navigator object with AI"), gesture="kb:NVDA+alt+shift+t")
	def script_table(self, gesture):
		obj = _webNavigator()
		if obj:
			onMatched = lambda located: _askModel({"type": "table", "elementId": located["elementId"]})  # noqa: E731
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, onMatched)

	# Translators: input gesture description.
	@script(description=_("Explains the chart around the navigator object with AI"), gesture="kb:NVDA+alt+shift+d")
	def script_chart(self, gesture):
		obj = _webNavigator()
		if obj:
			onMatched = lambda located: _askModel({"type": "chart", "elementId": located["elementId"]})  # noqa: E731
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, onMatched)

	# Translators: input gesture description.
	@script(description=_("Writes an accessibility issue report about the navigator object for the site, to the clipboard"), gesture="kb:NVDA+alt+shift+s")
	def script_report(self, gesture):
		obj = _webNavigator()
		if obj:
			self._locate(obj, {"type": "locate", "nav": _navContext(obj)}, _report)

	# Translators: input gesture description.
	@script(description=_("Saves the last element explanation for this site, or deletes a saved one"), gesture="kb:NVDA+alt+shift+k")
	def script_label(self, gesture):
		threading.Thread(target=_toggleLabel, daemon=True).start()

	# Translators: input gesture description.
	@script(description=_("Starts a guided task: AI tells each step and moves focus, you act"), gesture="kb:NVDA+alt+shift+g")
	def script_guide(self, gesture):
		if not _browserFocused():
			return
		# Translators: prompt of the guided task dialog.
		wx.CallAfter(_askText, _("What do you want to do on this page?"), lambda goal: _guide({"type": "guide", "query": goal}))

	# Translators: input gesture description.
	@script(description=_("Asks for the next step of the guided task"), gesture="kb:NVDA+alt+shift+n")
	def script_guideNext(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_guide, args=({"type": "guide_next"},), daemon=True).start()

	# Translators: input gesture description.
	@script(description=_("Summarizes the current web page with AI"), gesture="kb:NVDA+alt+shift+p")
	def script_summarize(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_askModel, args=({"type": "summarize"},), daemon=True).start()

	# Translators: input gesture description.
	@script(description=_("Finds something on the web page with AI and moves there"), gesture="kb:NVDA+alt+shift+f")
	def script_find(self, gesture):
		if not _browserFocused():
			return
		# Translators: prompt of the find dialog.
		wx.CallAfter(_askText, _("What are you looking for on the page?"), _find)

	# Translators: input gesture description.
	@script(description=_("Says what changed on the page since the last click or key press"), gesture="kb:NVDA+alt+shift+c")
	def script_changes(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_askModel, args=({"type": "changes"},), daemon=True).start()

	# Translators: input gesture description.
	@script(description=_("Lists the parts of the page found by AI and moves to one"), gesture="kb:NVDA+alt+shift+b")
	def script_sections(self, gesture):
		if not _browserFocused():
			return
		threading.Thread(target=_sections, daemon=True).start()

	# Translators: input gesture description.
	@script(description=_("Asks a follow-up question about the last AI answer"), gesture="kb:NVDA+alt+shift+q")
	def script_followup(self, gesture):
		wx.CallAfter(
			_askText,
			# Translators: prompt of the follow-up question dialog.
			_("What do you want to ask about the last AI answer?"),
			lambda question: _askModel({"type": "followup", "query": question}),
		)

	# Translators: input gesture description.
	@script(description=_("Locates the navigator object in the page (for troubleshooting)"), gesture="kb:NVDA+alt+shift+l")
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
