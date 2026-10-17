"""Coordinator process.

Chrome starts it as the native messaging host (stdio). It also serves the NVDA add-on on
127.0.0.1 with one JSON line per request, authenticated by a token in the session file.
"""

import hashlib
import hmac
import json
import logging
import os
import queue
import re
import secrets
import socketserver
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

import llm
import native
from grounding import resolve
from privacy import redact

DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "nvda-ai-copilot"
# shortcut: one session file per user, so the last started Chrome profile wins; key by profile if needed.
SESSION_FILE = DATA_DIR / "session.json"
EXTENSION_TIMEOUT_S = 3
CLIENT_TIMEOUT_S = 5
MAX_REQUEST_BYTES = 64 * 1024
MAX_QUERY_CHARS = 300
# A follow-up is about the answer the person just heard; after this the page has likely moved on.
FOLLOWUP_TTL_S = 300
# Same element, same state, same answer: repeat questions are spoken at once and cost nothing.
CACHED_TASKS = {"explain"}
CACHE_SIZE = 200
CACHE_TTL_S = 30 * 60
MAX_BLOCKED_SITES = 200
SITE = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*")
LANGUAGE_CODE = re.compile(r"[A-Za-z]{2,3}([_-][A-Za-z0-9]{2,8})?")

log = logging.getLogger("coordinator")


class ExtensionError(Exception):
	pass


class Blocked(Exception):
	"""The page's site is on the person's blocked list: nothing from it may reach the model."""


def site_host(entry):
	"""'https://www.Bank.com/x', '*.bank.com' or 'bank.com' -> the host name, or None if it is not one."""
	entry = entry.strip().lower()
	host = (urlsplit(entry if "://" in entry else "//" + entry).hostname or "").lstrip("*.")
	return host if SITE.fullmatch(host) else None


def parse_settings(raw):
	"""The add-on's privacy and language settings; anything malformed falls back to the safe default."""
	raw = raw if isinstance(raw, dict) else {}
	sites = raw.get("blockedSites") if isinstance(raw.get("blockedSites"), list) else []
	hosts = [site_host(s) for s in sites[:MAX_BLOCKED_SITES] if isinstance(s, str)]
	language = raw.get("language")
	return {
		"screenshots": raw.get("screenshots") is not False,
		"blockedSites": [h for h in hosts if h],
		"language": language if isinstance(language, str) and LANGUAGE_CODE.fullmatch(language) else llm.DEFAULT_LANGUAGE,
	}


def is_blocked(origin, sites):
	host = (urlsplit(origin).hostname or "").lower()
	return any(host == s or host.endswith("." + s) for s in sites)


def info(code, text):
	"""A spoken notice that is not AI output; the add-on speaks its own translation of code."""
	return {"status": "info", "code": code, "text": text}


class Extension:
	"""Request/response over the native messaging pipe, matched by requestId."""

	def __init__(self, out):
		self.out = out
		self.lock = threading.Lock()
		self.waiting = {}
		self.next_id = 0

	def ask(self, msg):
		with self.lock:
			self.next_id += 1
			rid = self.next_id
			replies = queue.Queue(1)
			self.waiting[rid] = replies
			native.write_message(self.out, {**msg, "requestId": rid})
		try:
			reply = replies.get(timeout=EXTENSION_TIMEOUT_S)
		except queue.Empty:
			raise ExtensionError(f"extension did not answer {msg['type']}") from None
		finally:
			with self.lock:
				self.waiting.pop(rid, None)
		if not isinstance(reply, dict) or "error" in reply:
			raise ExtensionError(str(reply.get("error") if isinstance(reply, dict) else reply))
		return reply

	def on_message(self, msg):
		with self.lock:
			replies = self.waiting.get(msg.get("requestId")) if isinstance(msg, dict) else None
		if replies:
			replies.put(msg)


class Coordinator:
	def __init__(self, ask_extension, explain=None, choose=None, sections=None, followup=None):
		self.ask = ask_extension
		# The defaults answer in the person's language and stream sentences through self._emit.
		# explain(data, screenshot, task) -> spoken text
		self.explain_fn = explain or (
			lambda ctx, shot, task: llm.explain(llm.default_client(), ctx, shot, task, self.settings["language"], self._emit)
		)
		# choose(data, screenshot, user_request, choices) -> (element ID in choices or None, spoken reason)
		self.choose_fn = choose or (
			lambda ctx, shot, q, ids: llm.choose(llm.default_client(), ctx, shot, q, ids, self.settings["language"])
		)
		# sections(data, screenshot, choices) -> [(element ID in choices, title)]
		self.sections_fn = sections or (
			lambda ctx, shot, ids: llm.sections(llm.default_client(), ctx, shot, ids, self.settings["language"])
		)
		# followup(data, screenshot, task, turns, question) -> spoken text
		self.followup_fn = followup or (
			lambda *a: llm.followup(llm.default_client(), *a, self.settings["language"], self._emit)
		)
		self.settings = parse_settings(None)  # replaced by each request's settings
		self._emit = None  # sentence callback of the current request, if the client streams
		self.streamed = False
		self.pending = None  # (nonce, snapshot) of the marking round the add-on is polling
		self.last = None  # model input and turns of the last AI answer, for follow-up questions
		self.section_ids = set()  # IDs of the last section list: the only elements "focus" may move to
		self.cache = OrderedDict()  # hash of task and redacted model data -> (answer, time)

	def handle(self, req, emit=None):
		"""emit(text), if given, receives finished sentences of the answer while it is written."""
		self.settings = parse_settings(req.get("settings"))
		self.streamed = False

		def on_sentence(text):
			self.streamed = True
			emit(text)

		self._emit = on_sentence if emit else None
		reply = self._handle(req)
		if self.streamed and reply.get("status") == "explained":
			reply["streamed"] = True  # the add-on already spoke it
		return reply

	def _handle(self, req):
		kind = req.get("type")
		try:
			if kind == "locate" and isinstance(req.get("nav"), dict):
				return self.locate(req["nav"], req.get("nonce"))
			if kind == "explain" and isinstance(req.get("elementId"), str):
				return self.explain(req["elementId"])
			if kind == "summarize":
				return self.summarize()
			if kind == "form" and isinstance(req.get("elementId"), str):
				ctx = self._page({"type": "form", "elementId": req["elementId"]})
				return {"status": "explained", "text": self._ask_model(ctx, "form", "form")}
			if kind == "table" and isinstance(req.get("elementId"), str):
				ctx = self._page({"type": "table", "elementId": req["elementId"]})
				if not ctx.get("table"):
					return info("no_table", "there is no table in or around this element")
				return {"status": "explained", "text": self._ask_model(ctx, "table", "table")}
			if kind == "changes":
				ctx = self._page({"type": "changes"})
				if not ctx["changes"]["items"]:
					return info("no_changes", "nothing visible changed since the last click or key press")
				return {"status": "explained", "text": self._ask_model(ctx, "changes", "changes")}
			if kind == "sections":
				return self.sections()
			if kind == "focus" and req.get("elementId") in self.section_ids:
				focused = self.ask({"type": "focus", "elementId": req["elementId"]}).get("focused")
				return {"status": "focused", "elementId": req["elementId"], "focused": bool(focused)}
			query = req.get("query")
			if isinstance(query, str) and 0 < len(query.strip()) <= MAX_QUERY_CHARS:
				if kind == "find":
					return self.find(query.strip())
				if kind == "followup":
					return self.followup(query.strip())
			return {"status": "error", "code": "bad_request", "message": "bad request"}
		except Blocked:
			return info("blocked", "Copilot is turned off for this site in the NVDA settings")
		except ExtensionError as e:
			return {"status": "error", "code": "extension", "message": str(e)}
		except llm.LLMError as e:
			return {"status": "error", "code": e.code, "message": str(e)}
		except (KeyError, TypeError, ValueError) as e:
			log.exception("%s failed", kind)
			return {"status": "error", "code": "bad_data", "message": f"bad data: {e}"}

	def explain(self, element_id):
		ctx = self._page({"type": "context", "elementId": element_id})
		text = self._ask_model(ctx, "element", "explain")
		return {"status": "explained", "elementId": element_id, "text": text}

	def summarize(self):
		ctx = self._page({"type": "outline"})
		return {"status": "explained", "text": self._ask_model(ctx, "outline", "summarize")}

	def find(self, query):
		ctx = self._page({"type": "outline"})
		outline = ctx["outline"]
		# The model may only pick an element the extension listed; "focus" is the only action allowed.
		choices = sorted({item["id"] for part in ("headings", "landmarks", "controls") for item in outline[part]})
		data = redact({"page": ctx["page"], "outline": outline})
		shot = ctx.get("screenshot")
		# Queries and AI text are not logged: they describe what the user is doing on the page.
		log.info("find: %s choices, screenshot=%s chars", len(choices), len(shot or ""))
		element_id, reason = self.choose_fn(data, shot, query, choices)
		log.info("find -> %s", element_id)
		self._remember("summarize", data, shot, query, reason)
		if element_id is None:
			return {"status": "none", "text": reason}
		focused = self.ask({"type": "focus", "elementId": element_id}).get("focused")
		return {"status": "found", "elementId": element_id, "focused": bool(focused), "text": reason}

	def sections(self):
		ctx = self._page({"type": "sections"})
		sections = ctx["sections"]
		# As with find: only IDs the extension issued, and "focus" is the only action on them.
		choices = sorted({item["id"] for part in ("headings", "landmarks", "blocks") for item in sections[part]})
		if not choices:
			return info("no_sections", "the page has no content to split into parts")
		data = redact({"page": ctx["page"], "sections": sections})
		shot = ctx.get("screenshot")
		picked = self.sections_fn(data, shot, choices)
		log.info("sections: %s choices -> %s", len(choices), len(picked))
		if not picked:
			return info("no_sections", "the page could not be split into parts")
		self.section_ids = {element_id for element_id, _ in picked}
		self._remember("summarize", data, shot, None, "Parts of the page: " + "; ".join(t for _, t in picked))
		return {"status": "sections", "sections": [{"elementId": i, "title": t} for i, t in picked]}

	def followup(self, question):
		last = self.last
		if not last or time.monotonic() - last["at"] > FOLLOWUP_TTL_S:
			return info("no_followup", "a follow-up asks about the last AI answer; use an AI command first")
		if is_blocked(last["data"]["page"]["origin"], self.settings["blockedSites"]):
			raise Blocked()
		shot = last["shot"] if self.settings["screenshots"] else None
		text = self.followup_fn(last["data"], shot, last["task"], list(last["turns"]), question)
		log.info("followup %s -> %s chars", len(last["turns"]), len(text))
		last["turns"].append((question, text))
		return {"status": "explained", "text": text}

	def _page(self, msg):
		"""Page data from the extension, with the person's privacy settings applied before any of it
		can reach the model."""
		ctx = self.ask(msg if self.settings["screenshots"] else {**msg, "screenshot": False})
		if is_blocked(ctx["page"]["origin"], self.settings["blockedSites"]):
			raise Blocked()
		if not self.settings["screenshots"]:
			ctx["screenshot"] = None
		return ctx

	def _remember(self, task, data, shot, request, answer):
		self.last = {"task": task, "data": data, "shot": shot, "turns": [(request, answer)], "at": time.monotonic()}

	def _ask_model(self, ctx, key, task):
		if ctx.get("screenshotError"):
			log.warning("screenshot failed: %s", ctx["screenshotError"])
		# Only these keys may reach the model; redact() is the last filter before it.
		data = redact({"page": ctx["page"], key: ctx[key]})
		shot = ctx.get("screenshot")
		log.info("%s: screenshot=%s chars, data=%s chars", task, len(shot or ""), len(json.dumps(data)))
		cache_input = [task, data, self.settings["language"]]
		key = hashlib.sha256(json.dumps(cache_input, sort_keys=True).encode()).hexdigest() if task in CACHED_TASKS else None
		hit = self.cache.get(key)
		if hit and time.monotonic() - hit[1] < CACHE_TTL_S:
			self.cache.move_to_end(key)
			text = hit[0]
			log.info("%s -> cached", task)
		else:
			text = self.explain_fn(data, shot, task)
			log.info("%s -> %s chars", task, len(text))
			if key:
				self.cache[key] = (text, time.monotonic())
				while len(self.cache) > CACHE_SIZE:
					self.cache.popitem(last=False)
		self._remember(task, data, shot, None, text)
		return text

	def locate(self, nav, nonce=None):
		pending, self.pending = self.pending, None
		if pending and pending[0] != nonce:
			self.ask({"type": "clear", "nonce": pending[0]})  # abandoned round
			pending = None
		if pending:
			snap = pending[1]
		else:
			nonce = None
			snap = self.ask({"type": "snapshot"})
		try:
			m = resolve(nav, snap["elements"], snap["dpr"], nonce)
		finally:
			if nonce:
				self.ask({"type": "clear", "nonce": nonce})
		log.info("locate nav=%s nonce=%s -> %s", nav, nonce, m)
		if m.status == "ambiguous" and not nonce:
			new_nonce = secrets.token_hex(4)
			self.ask({"type": "mark", "ids": m.candidates, "nonce": new_nonce})
			self.pending = (new_nonce, snap)
			return {"status": "ambiguous", "nonce": new_nonce, "candidates": m.candidates}
		el = next((e for e in snap["elements"] if e["id"] == m.element_id), None)
		return {
			"status": m.status,
			"elementId": m.element_id,
			"method": m.method,
			"tag": el["tag"] if el else None,
			"candidates": m.candidates,
		}


class Handler(socketserver.StreamRequestHandler):
	timeout = CLIENT_TIMEOUT_S

	def handle(self):
		try:
			req = json.loads(self.rfile.readline(MAX_REQUEST_BYTES))
		except (OSError, ValueError):
			return
		if not isinstance(req, dict) or not hmac.compare_digest(
			str(req.get("token", "")).encode(), self.server.token.encode()
		):
			log.warning("rejected client without valid token")
			return

		def emit(text):
			try:
				self.wfile.write((json.dumps({"status": "partial", "text": text}) + "\n").encode("utf-8"))
			except OSError:
				pass  # the add-on stopped waiting; the full answer is still cached and remembered

		reply = self.server.coordinator.handle(req, emit)
		self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))


def main():
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	logging.basicConfig(
		filename=DATA_DIR / "coordinator.log",
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(message)s",
	)
	ext = Extension(sys.stdout.buffer)
	server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
	server.token = secrets.token_hex(32)
	server.coordinator = Coordinator(ext.ask)
	SESSION_FILE.write_text(json.dumps({"port": server.server_address[1], "token": server.token, "pid": os.getpid()}))
	threading.Thread(target=server.serve_forever, daemon=True).start()
	log.info("started, port %s", server.server_address[1])
	try:
		while (msg := native.read_message(sys.stdin.buffer)) is not None:
			ext.on_message(msg)
	finally:
		try:
			if json.loads(SESSION_FILE.read_text()).get("token") == server.token:
				SESSION_FILE.unlink()
		except (OSError, ValueError):
			pass
		log.info("Chrome closed the pipe, exiting")


if __name__ == "__main__":
	main()
