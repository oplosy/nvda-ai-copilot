import io
import threading
import unittest

import native
from host import Coordinator, Extension, ExtensionError

SNAPSHOT = {
	"dpr": 1.0,
	"elements": [
		{"id": "e_1", "tag": "button", "htmlId": "go", "rect": [10, 10, 80, 30]},
		{"id": "e_4", "tag": "div", "htmlId": None, "rect": [200, 10, 40, 40]},
		{"id": "e_5", "tag": "div", "htmlId": None, "rect": [200, 10, 40, 40]},
	],
}


def nav(rect, tag, classes=None):
	return {"tag": tag, "htmlId": None, "classes": classes, "screenRect": rect, "viewportOrigin": [0, 0]}


class FakeExtension:
	def __init__(self):
		self.sent = []

	def ask(self, msg):
		self.sent.append(msg)
		return SNAPSHOT if msg["type"] == "snapshot" else {"ok": True}


class CoordinatorTest(unittest.TestCase):
	def setUp(self):
		self.ext = FakeExtension()
		self.c = Coordinator(self.ext.ask)

	def types(self):
		return [m["type"] for m in self.ext.sent]

	def test_direct_match_needs_no_markers(self):
		r = self.c.handle({"type": "locate", "nav": nav([10, 10, 80, 30], "button")})
		self.assertEqual((r["status"], r["elementId"], r["tag"]), ("matched", "e_1", "button"))
		self.assertEqual(self.types(), ["snapshot"])

	def test_ambiguous_round_marks_then_resolves_and_clears(self):
		r = self.c.handle({"type": "locate", "nav": nav([200, 10, 40, 40], "div")})
		self.assertEqual(r["status"], "ambiguous")
		nonce = r["nonce"]
		self.assertEqual(self.ext.sent[-1], {"type": "mark", "ids": ["e_4", "e_5"], "nonce": nonce})
		r = self.c.handle(
			{"type": "locate", "nav": nav([200, 10, 40, 40], "div", f"site nvai-{nonce}-e_5"), "nonce": nonce}
		)
		self.assertEqual((r["status"], r["elementId"], r["method"]), ("matched", "e_5", "marker"))
		self.assertEqual(self.types(), ["snapshot", "mark", "clear"])

	def test_abandoned_round_is_cleared(self):
		nonce = self.c.handle({"type": "locate", "nav": nav([200, 10, 40, 40], "div")})["nonce"]
		self.c.handle({"type": "locate", "nav": nav([10, 10, 80, 30], "button")})
		self.assertEqual(self.ext.sent[2], {"type": "clear", "nonce": nonce})
		self.assertEqual(self.types()[3], "snapshot")

	def test_extension_error_is_reported(self):
		def failing(msg):
			raise ExtensionError("no content script")

		r = Coordinator(failing).handle({"type": "locate", "nav": nav([0, 0, 1, 1], "a")})
		self.assertEqual(r, {"status": "error", "code": "extension", "message": "no content script"})

	def test_bad_request(self):
		self.assertEqual(self.c.handle({"type": "nope"})["status"], "error")


class ExtensionBridgeTest(unittest.TestCase):
	def test_reply_is_matched_by_request_id(self):
		out = io.BytesIO()
		ext = Extension(out)
		result = {}
		t = threading.Thread(target=lambda: result.update(ext.ask({"type": "snapshot"})))
		t.start()
		while not ext.waiting:
			pass
		with ext.lock:  # ask() writes the request while holding the lock
			pass
		sent = native.read_message(io.BytesIO(out.getvalue()))
		ext.on_message({"requestId": 999, "dpr": 2})  # stray reply is ignored
		ext.on_message({"requestId": sent["requestId"], "dpr": 1})
		t.join(2)
		self.assertEqual(result, {"requestId": sent["requestId"], "dpr": 1})


class NativeFramingTest(unittest.TestCase):
	def test_roundtrip_and_eof(self):
		buf = io.BytesIO()
		native.write_message(buf, {"type": "mark", "ids": ["e_1"], "text": "ğüş"})
		buf.seek(0)
		self.assertEqual(native.read_message(buf), {"type": "mark", "ids": ["e_1"], "text": "ğüş"})
		self.assertIsNone(native.read_message(buf))


if __name__ == "__main__":
	unittest.main()
