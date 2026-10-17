"""Coordinator process.

Chrome starts it as the native messaging host (stdio). It also serves the NVDA add-on on
127.0.0.1 with one JSON line per request, authenticated by a token in the session file.
"""

import hmac
import json
import logging
import os
import queue
import secrets
import socketserver
import sys
import threading
from pathlib import Path

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

log = logging.getLogger("coordinator")


class ExtensionError(Exception):
	pass


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
	def __init__(self, ask_extension, explain=None, choose=None):
		self.ask = ask_extension
		# explain(data, screenshot, task) -> spoken text
		self.explain_fn = explain or (lambda ctx, shot, task: llm.explain(llm.default_client(), ctx, shot, task))
		# choose(data, screenshot, user_request, choices) -> (element ID in choices or None, spoken reason)
		self.choose_fn = choose or (lambda ctx, shot, q, ids: llm.choose(llm.default_client(), ctx, shot, q, ids))
		self.pending = None  # (nonce, snapshot) of the marking round the add-on is polling

	def handle(self, req):
		kind = req.get("type")
		try:
			if kind == "locate" and isinstance(req.get("nav"), dict):
				return self.locate(req["nav"], req.get("nonce"))
			if kind == "explain" and isinstance(req.get("elementId"), str):
				return self.explain(req["elementId"])
			if kind == "summarize":
				return self.summarize()
			if kind == "form" and isinstance(req.get("elementId"), str):
				ctx = self.ask({"type": "form", "elementId": req["elementId"]})
				return {"status": "explained", "text": self._ask_model(ctx, "form", "form")}
			query = req.get("query")
			if kind == "find" and isinstance(query, str) and 0 < len(query.strip()) <= MAX_QUERY_CHARS:
				return self.find(query.strip())
			return {"status": "error", "message": "bad request"}
		except (ExtensionError, llm.LLMError) as e:
			return {"status": "error", "message": str(e)}
		except (KeyError, TypeError, ValueError) as e:
			log.exception("%s failed", kind)
			return {"status": "error", "message": f"bad data: {e}"}

	def explain(self, element_id):
		ctx = self.ask({"type": "context", "elementId": element_id})
		text = self._ask_model(ctx, "element", "explain")
		return {"status": "explained", "elementId": element_id, "text": text}

	def summarize(self):
		ctx = self.ask({"type": "outline"})
		return {"status": "explained", "text": self._ask_model(ctx, "outline", "summarize")}

	def find(self, query):
		ctx = self.ask({"type": "outline"})
		outline = ctx["outline"]
		# The model may only pick an element the extension listed; "focus" is the only action allowed.
		choices = sorted({item["id"] for part in ("headings", "landmarks", "controls") for item in outline[part]})
		data = redact({"page": ctx["page"], "outline": outline})
		shot = ctx.get("screenshot")
		# Queries and AI text are not logged: they describe what the user is doing on the page.
		log.info("find: %s choices, screenshot=%s chars", len(choices), len(shot or ""))
		element_id, reason = self.choose_fn(data, shot, query, choices)
		log.info("find -> %s", element_id)
		if element_id is None:
			return {"status": "none", "text": reason}
		focused = self.ask({"type": "focus", "elementId": element_id}).get("focused")
		return {"status": "found", "elementId": element_id, "focused": bool(focused), "text": reason}

	def _ask_model(self, ctx, key, task):
		if ctx.get("screenshotError"):
			log.warning("screenshot failed: %s", ctx["screenshotError"])
		# Only these keys may reach the model; redact() is the last filter before it.
		data = redact({"page": ctx["page"], key: ctx[key]})
		shot = ctx.get("screenshot")
		log.info("%s: screenshot=%s chars, data=%s chars", task, len(shot or ""), len(json.dumps(data)))
		text = self.explain_fn(data, shot, task)
		log.info("%s -> %s chars", task, len(text))
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
		reply = self.server.coordinator.handle(req)
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
