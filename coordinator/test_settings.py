"""Privacy and language settings from the add-on, and streamed answers."""

import json
import unittest
from types import SimpleNamespace

import llm
from host import Coordinator, parse_settings, site_host

PAGE = {"origin": "https://online.bank.example", "title": "Hesap"}
CONTEXT = {"page": PAGE, "element": {"tag": "div"}, "screenshot": "shot"}


class SettingsTest(unittest.TestCase):
	def test_malformed_settings_fall_back_to_defaults(self):
		default = {"screenshots": True, "blockedSites": [], "language": "tr"}
		for raw in (None, "x", {"screenshots": "no", "blockedSites": "bank.example", "language": "../etc"}):
			self.assertEqual(parse_settings(raw), default)

	def test_sites_are_normalized_and_bad_entries_dropped(self):
		self.assertEqual(site_host("https://www.Bank.example:8443/login?x=1"), "www.bank.example")
		self.assertEqual(site_host("*.bank.example"), "bank.example")
		self.assertIsNone(site_host("not a site"))
		s = parse_settings({"blockedSites": ["bank.example", "bad site", 5], "screenshots": False, "language": "pt_BR"})
		self.assertEqual(s, {"screenshots": False, "blockedSites": ["bank.example"], "language": "pt_BR"})

	def test_blocked_site_never_reaches_the_model(self):
		c = Coordinator(lambda msg: dict(CONTEXT), explain=lambda *a: self.fail("model called"))
		r = c.handle({"type": "explain", "elementId": "e_1", "settings": {"blockedSites": ["bank.example"]}})
		self.assertEqual((r["status"], r["code"]), ("info", "blocked"))

	def test_followup_on_a_now_blocked_site_is_refused(self):
		c = Coordinator(lambda msg: dict(CONTEXT), explain=lambda *a: "x", followup=lambda *a: self.fail("model called"))
		c.handle({"type": "explain", "elementId": "e_1"})
		r = c.handle({"type": "followup", "query": "?", "settings": {"blockedSites": ["online.bank.example"]}})
		self.assertEqual(r["code"], "blocked")

	def test_screenshots_off_are_not_taken_or_sent(self):
		sent, seen = [], {}
		c = Coordinator(lambda msg: sent.append(msg) or dict(CONTEXT), explain=lambda d, shot, t: seen.update(shot=shot) or "x")
		c.handle({"type": "explain", "elementId": "e_1", "settings": {"screenshots": False}})
		self.assertEqual(sent, [{"type": "context", "elementId": "e_1", "screenshot": False}])
		self.assertIsNone(seen["shot"])

	def test_language_reaches_the_prompt_and_the_cache_key(self):
		self.assertIn("Answer in German", llm.build_request({}, None, "explain", language="de")["system"])
		calls = []
		c = Coordinator(lambda msg: json.loads(json.dumps(CONTEXT)), explain=lambda *a: calls.append(a) or "x")
		for language in ("tr", "tr", "en"):
			c.handle({"type": "explain", "elementId": "e_1", "settings": {"language": language}})
		self.assertEqual(len(calls), 2)


class StreamingTest(unittest.TestCase):
	def test_sentences_are_emitted_as_they_finish(self):
		class Stream:
			text_stream = iter(["Bu bir ", "düğme. Sepete", " ekler! Son", " kısım"])

			def __enter__(self):
				return self

			def __exit__(self, *exc):
				return False

			def get_final_message(self):
				return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Bu bir düğme. Sepete ekler! Son kısım")])

		client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream())))
		spoken = []
		text = llm.explain(client, {}, None, on_sentence=spoken.append)
		self.assertEqual(spoken, ["Bu bir düğme.", "Sepete ekler!", "Son kısım"])
		self.assertEqual(text, "Bu bir düğme. Sepete ekler! Son kısım")

	def test_streamed_reply_is_marked_and_cached_reply_is_not(self):
		emitted = []
		holder = {}

		def explain(data, shot, task):
			holder["c"]._emit("Bir düğme.")
			return "Bir düğme."

		c = holder["c"] = Coordinator(lambda msg: json.loads(json.dumps(CONTEXT)), explain=explain)
		r = c.handle({"type": "explain", "elementId": "e_1"}, emitted.append)
		self.assertEqual((r["text"], r.get("streamed"), emitted), ("Bir düğme.", True, ["Bir düğme."]))
		r = c.handle({"type": "explain", "elementId": "e_1"}, emitted.append)  # cache hit: nothing streamed
		self.assertNotIn("streamed", r)
		self.assertEqual(len(emitted), 1)


if __name__ == "__main__":
	unittest.main()
