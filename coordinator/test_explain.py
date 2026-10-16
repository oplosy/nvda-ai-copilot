import json
import unittest
from types import SimpleNamespace

import llm
from host import Coordinator
from privacy import CARD_MASK, redact

CONTEXT = {
	"page": {"origin": "https://shop.example", "title": "Sepet"},
	"element": {"tag": "div", "role": "button", "text": "", "value": "secret", "nearby": {"parent": "Kart: 4111 1111 1111 1111"}},
	"rect": [0, 0, 10, 10],
	"viewport": [100, 100],
	"sensitiveRects": [],
	"screenshot": "iVBOR",
	"requestId": 3,
}


class PrivacyTest(unittest.TestCase):
	def test_card_numbers_masked_only_when_luhn_valid(self):
		self.assertEqual(redact("kart 4111-1111-1111-1111 son"), f"kart {CARD_MASK} son")
		self.assertEqual(redact("sipariş 1234567890123"), "sipariş 1234567890123")
		self.assertEqual(redact("tel 0532 123 45 67"), "tel 0532 123 45 67")

	def test_value_fields_dropped_recursively(self):
		self.assertEqual(redact({"a": [{"value": "x", "b": "y"}], "defaultValue": "z"}), {"a": [{"b": "y"}]})


class FakeClient:
	def __init__(self, response):
		self.calls = []
		self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
		self.response = response

	def _create(self, **kwargs):
		self.calls.append(kwargs)
		return self.response


def response(stop_reason="end_turn", text="Sepete ekle düğmesi."):
	blocks = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
	return SimpleNamespace(stop_reason=stop_reason, content=blocks)


class LLMTest(unittest.TestCase):
	def test_request_marks_page_data_untrusted_and_includes_image(self):
		req = llm.build_request({"element": {"tag": "a"}}, "iVBOR")
		self.assertEqual(req["model"], "claude-opus-5-5")
		self.assertEqual(req["fallbacks"], "default")
		self.assertIn("untrusted", req["system"])
		image, text = req["messages"][0]["content"]
		self.assertEqual(image["source"]["data"], "iVBOR")
		self.assertIn('<page_data>\n{"element": {"tag": "a"}}\n</page_data>', text["text"])

	def test_no_image_block_without_screenshot(self):
		req = llm.build_request({}, None)
		self.assertEqual([b["type"] for b in req["messages"][0]["content"]], ["text"])

	def test_explain_returns_text_blocks_only(self):
		self.assertEqual(llm.explain(FakeClient(response()), {}, None), "Sepete ekle düğmesi.")

	def test_missing_credentials_is_an_llm_error(self):
		import anthropic

		client = anthropic.Anthropic(api_key=None, auth_token=None)
		with self.assertRaises(llm.LLMError) as cm:
			llm.explain(client, {}, None)
		self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))

	def test_refusal_is_an_error(self):
		with self.assertRaises(llm.LLMError):
			llm.explain(FakeClient(response(stop_reason="refusal", text="")), {}, None)


class CoordinatorExplainTest(unittest.TestCase):
	def test_only_redacted_page_and_element_reach_the_model(self):
		seen = {}

		def fake_explain(data, shot, task):
			seen.update(data=data, shot=shot, task=task)
			return "Sepete ekle düğmesi."

		c = Coordinator(lambda msg: dict(CONTEXT), explain=fake_explain)
		r = c.handle({"type": "explain", "elementId": "e_7"})
		self.assertEqual(r, {"status": "explained", "elementId": "e_7", "text": "Sepete ekle düğmesi."})
		self.assertEqual(set(seen["data"]), {"page", "element"})
		dumped = json.dumps(seen["data"], ensure_ascii=False)
		self.assertNotIn("secret", dumped)
		self.assertNotIn("4111", dumped)
		self.assertEqual(seen["shot"], "iVBOR")

	def test_summarize_sends_only_redacted_page_and_outline(self):
		outline_ctx = {
			"page": {"origin": "https://shop.example", "title": "Sepet"},
			"outline": {"mainText": "Kart 4111 1111 1111 1111", "controls": [{"name": "Öde", "value": "x"}]},
			"rect": [0, 0, 100, 100],
			"screenshot": "iVBOR",
		}
		seen = {}

		def fake(data, shot, task):
			seen.update(data=data, task=task)
			return "Bir sepet sayfası."

		r = Coordinator(lambda msg: dict(outline_ctx), explain=fake).handle({"type": "summarize"})
		self.assertEqual(r, {"status": "explained", "text": "Bir sepet sayfası."})
		self.assertEqual((set(seen["data"]), seen["task"]), ({"page", "outline"}, "summarize"))
		dumped = json.dumps(seen["data"], ensure_ascii=False)
		self.assertNotIn("4111", dumped)
		self.assertNotIn('"value"', dumped)

	def test_summarize_prompt_differs_from_explain(self):
		s = llm.build_request({}, None, "summarize")
		e = llm.build_request({}, None)
		self.assertNotEqual(s["system"], e["system"])
		self.assertIn("untrusted", s["system"])
		self.assertTrue(s["messages"][0]["content"][-1]["text"].endswith("Bu sayfada ne var?"))

	def test_llm_error_is_reported(self):
		def failing(data, shot, task):
			raise llm.LLMError("anahtar yok")

		c = Coordinator(lambda msg: dict(CONTEXT), explain=failing)
		self.assertEqual(c.handle({"type": "explain", "elementId": "e_7"}), {"status": "error", "message": "anahtar yok"})


if __name__ == "__main__":
	unittest.main()
