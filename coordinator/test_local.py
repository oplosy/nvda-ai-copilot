"""Local model option: an OpenAI-compatible server on this computer, never a silent cloud fallback."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import llm
from host import Coordinator, parse_settings

LOCAL = {"provider": "local", "localUrl": "http://127.0.0.1:{port}/v1", "localModel": "qwen2.5vl:7b"}


class FakeServer(BaseHTTPRequestHandler):
	"""Answers /v1/chat/completions like Ollama: JSON, or server-sent events when stream is true."""

	requests = []
	answer = "Bu bir arama düğmesi. Büyüteç simgesine dayanıyorum."

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
		FakeServer.requests.append((self.path, body))
		if body["stream"]:
			self.send_response(200)
			self.send_header("Content-Type", "text/event-stream")
			self.end_headers()
			for piece in ("Bu bir arama ", "düğmesi. Büyüteç ", "simgesine dayanıyorum."):
				self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': piece}, 'finish_reason': None}]})}\n\n".encode())
			self.wfile.write(b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\ndata: [DONE]\n\n')
			return
		data = json.dumps({"choices": [{"message": {"content": FakeServer.answer}, "finish_reason": "stop"}]}).encode()
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def log_message(self, *args):
		pass


class LocalModelTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.server = HTTPServer(("127.0.0.1", 0), FakeServer)
		threading.Thread(target=cls.server.serve_forever, daemon=True).start()
		cls.settings = {**LOCAL, "localUrl": LOCAL["localUrl"].format(port=cls.server.server_address[1])}

	@classmethod
	def tearDownClass(cls):
		cls.server.shutdown()

	def setUp(self):
		FakeServer.requests.clear()

	def test_answer_and_image_go_to_the_local_server(self):
		client = llm.client_for(parse_settings(self.settings))
		text = llm.explain(client, {"page": {}}, "SU1H")
		self.assertEqual(text, FakeServer.answer)
		path, body = FakeServer.requests[0]
		self.assertEqual((path, body["model"], body["stream"]), ("/v1/chat/completions", "qwen2.5vl:7b", False))
		self.assertEqual(body["messages"][0]["role"], "system")
		self.assertEqual(body["messages"][1]["content"][0], {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,SU1H"}})

	def test_streamed_sentences_and_structured_choice(self):
		client = llm.client_for(parse_settings(self.settings))
		spoken = []
		llm.explain(client, {}, None, on_sentence=spoken.append)
		self.assertEqual(spoken, ["Bu bir arama düğmesi.", "Büyüteç simgesine dayanıyorum."])
		original, FakeServer.answer = FakeServer.answer, json.dumps({"elementId": "e_2", "reason": "Arama kutusu."})
		try:
			self.assertEqual(llm.choose(client, {}, None, "ara", ["e_2"]), ("e_2", "Arama kutusu."))
		finally:
			FakeServer.answer = original
		schema = FakeServer.requests[-1][1]["response_format"]["json_schema"]["schema"]
		self.assertEqual(schema["properties"]["elementId"]["enum"], ["e_2", "none"])

	def test_whole_command_through_the_coordinator(self):
		ctx = {"page": {"origin": "https://shop.example", "title": "x"}, "element": {"tag": "button"}, "screenshot": None}
		c = Coordinator(lambda msg: dict(ctx))
		emitted = []
		r = c.handle({"type": "explain", "elementId": "e_1", "settings": self.settings}, emitted.append)
		self.assertEqual((r["status"], r.get("streamed")), ("explained", True))
		self.assertEqual(emitted, ["Bu bir arama düğmesi.", "Büyüteç simgesine dayanıyorum."])

	def test_unreachable_or_non_local_server_never_falls_back_to_the_cloud(self):
		down = llm.client_for(parse_settings({**LOCAL, "localUrl": "http://127.0.0.1:9/v1"}))
		with self.assertRaises(llm.LLMError) as cm:
			llm.explain(down, {}, None)
		self.assertEqual(cm.exception.code, "local_unreachable")
		for bad in ({**LOCAL, "localUrl": "http://192.168.1.5:11434/v1"}, {**LOCAL, "localUrl": "https://api.example.com/v1"}, {**LOCAL, "localModel": "bad model!"}):
			with self.assertRaises(llm.LLMError) as cm:
				llm.client_for(parse_settings(bad))
			self.assertEqual(cm.exception.code, "local_invalid")


if __name__ == "__main__":
	unittest.main()
