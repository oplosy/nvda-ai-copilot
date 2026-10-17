"""Guided task: the model names the next step and its element, focus moves there, the person acts."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import host
import llm
from host import Coordinator

OUTLINE = {
	"page": {"origin": "https://shop.example", "title": "Ürün"},
	"outline": {
		"headings": [{"id": "e_1", "text": "Kulaklık"}],
		"landmarks": [],
		"controls": [{"id": "e_2", "name": "Sepete ekle"}, {"id": "e_3", "name": "Kart 4111 1111 1111 1111"}],
		"mainText": "",
	},
	"screenshot": "shot",
}
CHANGES = {"page": OUTLINE["page"], "changes": {"sinceSeconds": 3, "items": [{"kind": "added", "text": "Sepete eklendi"}]}}


class Extension:
	def __init__(self):
		self.sent = []

	def ask(self, msg):
		self.sent.append(msg)
		replies = {"outline": OUTLINE, "changes": CHANGES, "focus": {"focused": True}}
		return json.loads(json.dumps(replies[msg["type"]]))


class GuideTest(unittest.TestCase):
	def setUp(self):
		self.ext = Extension()
		self.steps = [("e_2", "Sepete ekle düğmesindesin, Enter'a bas.", False), (None, "Ürün sepete eklendi, görev bitti.", True)]
		self.seen = []

		def guide(data, shot, goal, steps, choices):
			self.seen.append({"data": data, "goal": goal, "steps": steps, "choices": choices})
			return self.steps[len(self.seen) - 1]

		self.c = Coordinator(self.ext.ask, guide=guide)

	def test_steps_move_focus_and_end_when_done(self):
		r = self.c.handle({"type": "guide", "query": " sepete ekle "})
		self.assertEqual(r, {"status": "guide", "text": "Sepete ekle düğmesindesin, Enter'a bas.", "elementId": "e_2", "focused": True, "done": False})
		self.assertEqual(self.seen[0]["goal"], "sepete ekle")
		self.assertEqual(self.seen[0]["choices"], ["e_1", "e_2", "e_3"])
		self.assertNotIn("4111", json.dumps(self.seen[0]["data"]))
		self.assertEqual(self.seen[0]["data"]["changesSinceLastStep"]["items"][0]["text"], "Sepete eklendi")
		self.assertIn({"type": "changes", "screenshot": False}, self.ext.sent)  # no second capture
		self.assertEqual(self.ext.sent[-1], {"type": "focus", "elementId": "e_2"})

		r = self.c.handle({"type": "guide_next"})
		self.assertEqual((r["done"], r["focused"], r["elementId"]), (True, None, None))
		self.assertEqual(self.seen[1]["steps"], [{"instruction": "Sepete ekle düğmesindesin, Enter'a bas.", "elementId": "e_2"}])
		self.assertEqual(self.c.handle({"type": "guide_next"})["code"], "no_guide")

	def test_guide_expires_and_is_capped(self):
		self.assertEqual(self.c.handle({"type": "guide_next"})["code"], "no_guide")
		self.c.handle({"type": "guide", "query": "sepete ekle"})
		with mock.patch.object(host.time, "monotonic", return_value=self.c.guide["at"] + host.GUIDE_TTL_S + 1):
			self.assertEqual(self.c.handle({"type": "guide_next"})["code"], "no_guide")
		self.c.guide = {"goal": "x", "steps": [{}] * host.MAX_GUIDE_STEPS, "at": host.time.monotonic()}
		self.assertEqual(self.c.handle({"type": "guide_next"})["code"], "guide_too_long")
		self.assertIsNone(self.c.guide)


class GuideRequestTest(unittest.TestCase):
	def client(self, text):
		calls = []

		def create(**kwargs):
			calls.append(kwargs)
			return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])

		return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)), calls=calls)

	def test_request_carries_goal_previous_steps_and_allowed_ids(self):
		c = self.client(json.dumps({"elementId": "e_9", "instruction": "Ara.", "done": False}))
		r = llm.guide(c, {}, None, "kulaklık al", [{"instruction": "Arama kutusuna yaz."}], ["e_1"])
		self.assertEqual(r, (None, "Ara.", False))  # an ID the extension did not issue is dropped
		req = c.calls[0]
		text = req["messages"][0]["content"][-1]["text"]
		self.assertIn("<user_request>\nkulaklık al\n</user_request>", text)
		self.assertIn('<previous_steps>\n["Arama kutusuna yaz."]\n</previous_steps>', text)
		self.assertEqual(req["output_config"]["format"]["schema"]["properties"]["elementId"]["enum"], ["e_1", "none"])
		self.assertIn("you never act", req["system"])

	def test_malformed_step_is_an_error(self):
		for text in ("{}", json.dumps({"elementId": "e_1", "instruction": " ", "done": False})):
			with self.assertRaises(llm.LLMError):
				llm.guide(self.client(text), {}, None, "x", [], ["e_1"])


if __name__ == "__main__":
	unittest.main()
