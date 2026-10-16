import json
import unittest
from types import SimpleNamespace

import llm
from host import Coordinator

OUTLINE_CTX = {
	"page": {"origin": "https://shop.example", "title": "Sepet"},
	"outline": {
		"headings": [{"id": "e_1", "level": 1, "text": "Sepetim"}],
		"landmarks": [{"id": "e_2", "role": "main", "name": ""}],
		"controls": [{"id": "e_3", "tag": "div", "name": "", "unlabeled": True}],
		"alerts": [],
		"mainText": "Kart 4111 1111 1111 1111",
	},
	"screenshot": "iVBOR",
}


class FakeExtension:
	def __init__(self):
		self.sent = []

	def ask(self, msg):
		self.sent.append(msg)
		if msg["type"] == "outline":
			return json.loads(json.dumps(OUTLINE_CTX))
		return {"focused": True}


def client_returning(text):
	resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])
	calls = []

	def create(**kwargs):
		calls.append(kwargs)
		return resp

	return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)), calls=calls)


class ChooseTest(unittest.TestCase):
	def test_schema_only_allows_given_ids_and_none(self):
		req = llm.build_request({}, None, "find", "sepete git", ["e_1", "e_3"])
		schema = req["output_config"]["format"]["schema"]
		self.assertEqual(schema["properties"]["elementId"]["enum"], ["e_1", "e_3", "none"])
		self.assertIn("<user_request>\nsepete git\n</user_request>", req["messages"][0]["content"][-1]["text"])

	def test_valid_choice(self):
		c = client_returning('{"elementId": "e_3", "reason": "Sepet düğmesini seçtim."}')
		self.assertEqual(llm.choose(c, {}, None, "sepet", ["e_1", "e_3"]), ("e_3", "Sepet düğmesini seçtim."))

	def test_invented_or_none_id_is_not_returned(self):
		c = client_returning('{"elementId": "e_99", "reason": "x"}')
		self.assertEqual(llm.choose(c, {}, None, "sepet", ["e_1"])[0], None)
		c = client_returning('{"elementId": "none", "reason": "Bulamadım."}')
		self.assertEqual(llm.choose(c, {}, None, "sepet", ["e_1"]), (None, "Bulamadım."))

	def test_malformed_output_is_an_error(self):
		with self.assertRaises(llm.LLMError):
			llm.choose(client_returning("not json"), {}, None, "sepet", ["e_1"])


class FindTest(unittest.TestCase):
	def test_found_element_is_focused(self):
		ext = FakeExtension()
		seen = {}

		def choose(data, shot, query, choices):
			seen.update(data=data, query=query, choices=choices)
			return "e_3", "Sepet düğmesine gittim."

		r = Coordinator(ext.ask, choose=choose).handle({"type": "find", "query": "  sepet  "})
		self.assertEqual(r, {"status": "found", "elementId": "e_3", "focused": True, "text": "Sepet düğmesine gittim."})
		self.assertEqual(seen["choices"], ["e_1", "e_2", "e_3"])
		self.assertEqual(seen["query"], "sepet")
		self.assertNotIn("4111", json.dumps(seen["data"]))
		self.assertEqual(ext.sent[-1], {"type": "focus", "elementId": "e_3"})

	def test_no_match_does_not_act(self):
		ext = FakeExtension()
		r = Coordinator(ext.ask, choose=lambda *a: (None, "Bulamadım.")).handle({"type": "find", "query": "x"})
		self.assertEqual(r, {"status": "none", "text": "Bulamadım."})
		self.assertEqual([m["type"] for m in ext.sent], ["outline"])

	def test_bad_queries_are_rejected(self):
		c = Coordinator(FakeExtension().ask, choose=lambda *a: ("e_1", ""))
		for query in ["", "   ", "x" * 301, None, 5]:
			self.assertEqual(c.handle({"type": "find", "query": query})["status"], "error")


if __name__ == "__main__":
	unittest.main()
