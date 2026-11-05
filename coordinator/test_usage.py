"""Monthly usage and estimated cost of Claude calls, and the optional monthly limit."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import llm
import usage
from host import Coordinator, parse_settings

NOV = time.mktime((2026, 11, 5, 12, 0, 0, 0, 0, -1))
DEC = time.mktime((2026, 12, 1, 12, 0, 0, 0, 0, -1))


def tokens(input=0, output=0, cache_write=0, cache_read=0):
	return SimpleNamespace(
		input_tokens=input, output_tokens=output, cache_creation_input_tokens=cache_write, cache_read_input_tokens=cache_read
	)


def answer(model="claude-opus-5-5", stop_reason="end_turn", used=None):
	return SimpleNamespace(
		model=model, stop_reason=stop_reason, usage=used or tokens(1000, 100), content=[SimpleNamespace(type="text", text="Bir düğme.")]
	)


class CostTest(unittest.TestCase):
	def test_cost_follows_the_price_table(self):
		self.assertAlmostEqual(usage.cost("claude-opus-5-5", tokens(1_000_000, 1_000_000)), 24.0)
		self.assertAlmostEqual(usage.cost("claude-sonnet-5-5", tokens(1_000_000, 1_000_000)), 12.0)
		self.assertAlmostEqual(usage.cost("claude-haiku-5-5", tokens(100_000, 1_000_000)), 0.51)  # prompt within the 100K tier

	def test_cache_reads_and_writes_are_priced(self):
		# Opus 5.5: cache write 1.25 x $4, cache read $0.20 per million tokens.
		self.assertAlmostEqual(usage.cost("claude-opus-5-5", tokens(cache_write=1_000_000, cache_read=1_000_000)), 5.2)

	def test_haiku_prompts_over_100k_tokens_cost_more(self):
		self.assertAlmostEqual(usage.cost("claude-haiku-5-5", tokens(100_000, 0)), 0.01)
		self.assertAlmostEqual(usage.cost("claude-haiku-5-5", tokens(200_000, 1_000_000)), 0.1 + 2.5)

	def test_missing_token_fields_count_as_zero(self):
		self.assertAlmostEqual(usage.cost("claude-opus-5-5", SimpleNamespace(input_tokens=1_000_000, output_tokens=None)), 4.0)

	def test_unknown_model_has_no_price(self):
		self.assertIsNone(usage.cost("gpt-x", tokens(1, 1)))


class UsageStoreTest(unittest.TestCase):
	def test_usage_adds_up_per_month_and_survives_a_restart(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp) / "usage.json"
			store = usage.Usage(path, clock=lambda: NOV)
			store.record("claude-opus-5-5", "claude-opus-5-5", tokens(1_000_000, 0))
			store.record("claude-haiku-5-5", "claude-haiku-5-5", tokens(0, 1_000_000))
			month = usage.Usage(path, clock=lambda: NOV).month()
			self.assertEqual(month["month"], "2026-11")
			self.assertEqual((month["requests"], month["inputTokens"], month["outputTokens"]), (2, 1_000_000, 1_000_000))
			self.assertAlmostEqual(month["costUsd"], 4.5)
			self.assertEqual(usage.Usage(path, clock=lambda: DEC).month()["requests"], 0)  # a new month starts at zero

	def test_a_second_coordinator_does_not_overwrite_the_first(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp) / "usage.json"
			a, b = usage.Usage(path, clock=lambda: NOV), usage.Usage(path, clock=lambda: NOV)
			a.record("claude-opus-5-5", "claude-opus-5-5", tokens(1, 1))
			b.record("claude-opus-5-5", "claude-opus-5-5", tokens(1, 1))
			self.assertEqual(usage.Usage(path, clock=lambda: NOV).month()["requests"], 2)

	def test_fallback_model_without_a_price_is_priced_as_the_requested_one(self):
		store = usage.Usage(clock=lambda: NOV)
		store.record("claude-some-fallback", "claude-sonnet-5-5", tokens(1_000_000, 0))
		self.assertAlmostEqual(store.month()["costUsd"], 2.0)

	def test_only_the_last_twelve_months_are_kept(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp) / "usage.json"
			for month in range(1, 15):
				clock = time.mktime((2025 + (month - 1) // 12, (month - 1) % 12 + 1, 10, 12, 0, 0, 0, 0, -1))
				usage.Usage(path, clock=lambda c=clock: c).record("claude-opus-5-5", "claude-opus-5-5", tokens(1, 1))
			kept = json.loads(path.read_text(encoding="utf-8"))
			self.assertEqual(len(kept), 12)
			self.assertNotIn("2025-01", kept)

	def test_unreadable_file_starts_empty(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp) / "usage.json"
			path.write_text("{not json", encoding="utf-8")
			self.assertEqual(usage.Usage(path, clock=lambda: NOV).month()["requests"], 0)
			path.write_text('{"2026-11": {"requests": "x"}}', encoding="utf-8")
			self.assertEqual(usage.Usage(path, clock=lambda: NOV).month()["requests"], 0)


class RecordingTest(unittest.TestCase):
	def setUp(self):
		self.store = usage.Usage(clock=lambda: NOV)
		patcher = mock.patch.object(llm, "usage_log", self.store)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_answers_are_recorded_with_the_model_that_served_them(self):
		client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: answer("claude-opus-5-5"))))
		llm.explain(client, {}, None, model="claude-opus-5-5")
		self.assertEqual(self.store.month()["requests"], 1)
		self.assertAlmostEqual(self.store.month()["costUsd"], (1000 * 4 + 100 * 20) / 1_000_000)

	def test_streamed_answers_are_recorded(self):
		class Stream:
			text_stream = iter(["Bir düğme."])

			def __enter__(self):
				return self

			def __exit__(self, *exc):
				return False

			def get_final_message(self):
				return answer()

		client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream())))
		llm.explain(client, {}, None, on_sentence=lambda s: None)
		self.assertEqual(self.store.month()["requests"], 1)

	def test_a_refusal_is_billed_so_it_is_recorded(self):
		client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: answer(stop_reason="refusal"))))
		with self.assertRaises(llm.LLMError):
			llm.explain(client, {}, None)
		self.assertEqual(self.store.month()["requests"], 1)

	def test_local_model_answers_cost_nothing_and_are_not_recorded(self):
		local = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Bir düğme.")])
		client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: local)))
		llm.explain(client, {}, None)
		self.assertEqual(self.store.month()["requests"], 0)

	def test_a_failing_usage_file_does_not_lose_the_answer(self):
		client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: answer())))
		with mock.patch.object(self.store, "record", side_effect=OSError("disk full")):
			self.assertEqual(llm.explain(client, {}, None), "Bir düğme.")


class LimitTest(unittest.TestCase):
	def setUp(self):
		self.store = usage.Usage(clock=lambda: NOV)
		self.store.record("claude-opus-5-5", "claude-opus-5-5", tokens(1_000_000, 0))  # $4 this month
		patcher = mock.patch.object(llm, "usage_log", self.store)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_limit_setting_is_validated(self):
		self.assertEqual(parse_settings({"monthlyLimit": 5})["monthlyLimit"], 5)
		self.assertEqual(parse_settings({"monthlyLimit": 2.5})["monthlyLimit"], 2.5)
		for bad in (None, "5", -1, True, float("nan"), float("inf"), 1e9):
			self.assertEqual(parse_settings({"monthlyLimit": bad})["monthlyLimit"], 0)

	def test_claude_is_not_called_once_the_limit_is_reached(self):
		with mock.patch.object(llm, "default_client", side_effect=AssertionError("client created")):
			with self.assertRaises(llm.LLMError) as e:
				llm.client_for({"provider": "claude", "monthlyLimit": 4})
		self.assertEqual(e.exception.code, "limit_reached")

	def test_below_the_limit_or_without_one_claude_is_used(self):
		with mock.patch.object(llm, "default_client", return_value="client"):
			self.assertEqual(llm.client_for({"provider": "claude", "monthlyLimit": 5}), "client")
			self.assertEqual(llm.client_for({"provider": "claude", "monthlyLimit": 0}), "client")

	def test_local_model_is_never_limited(self):
		client = llm.client_for({"provider": "local", "monthlyLimit": 1, "localUrl": "http://127.0.0.1:1/v1", "localModel": "m"})
		self.assertIsInstance(client, llm.LocalClient)

	def test_the_add_on_gets_a_limit_code(self):
		c = Coordinator(lambda msg: {"page": {"origin": "https://a.example"}, "element": {"tag": "div"}, "screenshot": None})
		r = c.handle({"type": "explain", "elementId": "e_1", "settings": {"monthlyLimit": 3}})
		self.assertEqual((r["status"], r["code"]), ("error", "limit_reached"))


if __name__ == "__main__":
	unittest.main()
