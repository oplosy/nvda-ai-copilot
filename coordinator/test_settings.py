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
		default = {"screenshots": True, "blockedSites": [], "language": "tr", "provider": "claude", "model": "claude-opus-5-5", "localUrl": "", "localModel": ""}
		for raw in (None, "x", {"screenshots": "no", "blockedSites": "bank.example", "language": "../etc"}):
			self.assertEqual(parse_settings(raw), default)

	def test_sites_are_normalized_and_bad_entries_dropped(self):
		self.assertEqual(site_host("https://www.Bank.example:8443/login?x=1"), "www.bank.example")
		self.assertEqual(site_host("*.bank.example"), "bank.example")
		self.assertIsNone(site_host("not a site"))
		s = parse_settings({"blockedSites": ["bank.example", "bad site", 5], "screenshots": False, "language": "pt_BR"})
		self.assertEqual(s, {"screenshots": False, "blockedSites": ["bank.example"], "language": "pt_BR", "provider": "claude", "model": "claude-opus-5-5", "localUrl": "", "localModel": ""})

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


class ModelChoiceTest(unittest.TestCase):
	def test_chosen_model_is_used_and_fallback_sent_only_where_it_exists(self):
		haiku = llm.build_request({}, None, "explain", model="claude-haiku-5-5")
		self.assertEqual(haiku["model"], "claude-haiku-5-5")
		self.assertNotIn("fallbacks", haiku)  # Haiku 5.5 has no server-side fallback; sending it fails
		self.assertNotIn("betas", haiku)
		for model in ("claude-sonnet-5-5", "claude-opus-5-5"):
			req = llm.build_request({}, None, "explain", model=model)
			self.assertEqual((req["fallbacks"], req["betas"]), ("default", [llm.FALLBACK_BETA]))

	def test_unknown_model_falls_back_to_the_default(self):
		self.assertEqual(parse_settings({"model": "claude-haiku-5-5"})["model"], "claude-haiku-5-5")
		self.assertEqual(parse_settings({"model": "gpt-x"})["model"], llm.MODEL)

	def test_model_reaches_the_request_and_the_cache_key(self):
		sent = []

		class Client:
			beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: sent.append(kw) or SimpleNamespace(
				stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Bir düğme.")]
			)))

		from unittest import mock

		with mock.patch.object(llm, "client_for", return_value=Client()):
			c = Coordinator(lambda msg: json.loads(json.dumps(CONTEXT)))
			for model in ("claude-haiku-5-5", "claude-haiku-5-5", "claude-opus-5-5"):
				c.handle({"type": "explain", "elementId": "e_1", "settings": {"model": model}})
		self.assertEqual([r["model"] for r in sent], ["claude-haiku-5-5", "claude-opus-5-5"])  # second one cached


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
