"""What changed, AI section list and follow-up questions."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import host
import llm
from host import Coordinator

PAGE = {"origin": "https://shop.example", "title": "Sepet"}
SECTIONS_CTX = {
	"page": PAGE,
	"sections": {
		"headings": [{"id": "e_1", "level": 1, "text": "Sepetim"}],
		"landmarks": [],
		"blocks": [{"id": "e_5", "tag": "div", "heading": "", "text": "Kart 4111 1111 1111 1111"}, {"id": "e_6", "tag": "div", "heading": "", "text": "Öneriler"}],
	},
	"screenshot": "shot",
}


class FakeExtension:
	def __init__(self, replies):
		self.replies = replies
		self.sent = []

	def ask(self, msg):
		self.sent.append(msg)
		return json.loads(json.dumps(self.replies[msg["type"]]))


def client_returning(text):
	calls = []

	def create(**kwargs):
		calls.append(kwargs)
		return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])

	return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)), calls=calls)


class ChangesTest(unittest.TestCase):
	def test_no_change_is_said_without_the_model(self):
		ext = FakeExtension({"changes": {"page": PAGE, "changes": {"sinceSeconds": 4, "items": [], "alerts": []}}})
		r = Coordinator(ext.ask, explain=lambda *a: self.fail("model called")).handle({"type": "changes"})
		self.assertEqual(r["status"], "info")

	def test_changes_reach_the_model_redacted(self):
		items = [{"kind": "added", "id": "e_9", "text": "Kart 4111 1111 1111 1111 kaydedildi", "secondsAgo": 1}]
		ext = FakeExtension({"changes": {"page": PAGE, "changes": {"sinceSeconds": 2, "items": items, "alerts": []}, "screenshot": "shot"}})
		seen = {}

		def explain(data, shot, task):
			seen.update(data=data, task=task)
			return "Kart kaydedildi mesajı çıktı."

		r = Coordinator(ext.ask, explain=explain).handle({"type": "changes"})
		self.assertEqual(r, {"status": "explained", "text": "Kart kaydedildi mesajı çıktı."})
		self.assertEqual((set(seen["data"]), seen["task"]), ({"page", "changes"}, "changes"))
		self.assertNotIn("4111", json.dumps(seen["data"]))


class SectionsTest(unittest.TestCase):
	def setUp(self):
		self.ext = FakeExtension({"sections": SECTIONS_CTX, "focus": {"focused": True}})
		self.seen = {}

		def sections(data, shot, choices):
			self.seen.update(data=data, choices=choices)
			return [("e_5", "Sepet"), ("e_6", "Öneriler")]

		self.c = Coordinator(self.ext.ask, sections=sections)

	def test_sections_are_listed_from_extension_ids(self):
		r = self.c.handle({"type": "sections"})
		self.assertEqual(r, {"status": "sections", "sections": [{"elementId": "e_5", "title": "Sepet"}, {"elementId": "e_6", "title": "Öneriler"}]})
		self.assertEqual(self.seen["choices"], ["e_1", "e_5", "e_6"])
		self.assertNotIn("4111", json.dumps(self.seen["data"]))

	def test_focus_only_moves_to_a_listed_section(self):
		self.assertEqual(self.c.handle({"type": "focus", "elementId": "e_5"})["status"], "error")  # nothing listed yet
		self.c.handle({"type": "sections"})
		self.assertEqual(self.c.handle({"type": "focus", "elementId": "e_1"})["status"], "error")  # offered, not picked
		self.assertEqual(self.c.handle({"type": "focus", "elementId": "e_6"}), {"status": "focused", "elementId": "e_6", "focused": True})
		self.assertEqual([m for m in self.ext.sent if m["type"] == "focus"], [{"type": "focus", "elementId": "e_6"}])

	def test_model_output_is_checked(self):
		c = client_returning(json.dumps({"sections": [
			{"elementId": "e_5", "title": " Sepet "},
			{"elementId": "e_99", "title": "Uydurma"},
			{"elementId": "e_5", "title": "Tekrar"},
			{"elementId": "e_6", "title": ""},
		]}))
		self.assertEqual(llm.sections(c, {}, None, ["e_5", "e_6"]), [("e_5", "Sepet")])
		schema = c.calls[0]["output_config"]["format"]["schema"]
		self.assertEqual(schema["properties"]["sections"]["items"]["properties"]["elementId"]["enum"], ["e_5", "e_6"])
		with self.assertRaises(llm.LLMError):
			llm.sections(client_returning("[]"), {}, None, ["e_5"])


class FollowupTest(unittest.TestCase):
	CONTEXT = {"page": PAGE, "element": {"tag": "div", "text": ""}, "screenshot": "shot"}

	def test_followups_continue_the_last_answer(self):
		calls = []

		def followup(data, shot, task, turns, question):
			calls.append((data, shot, task, turns, question))
			return f"Cevap {len(calls)}"

		c = Coordinator(lambda msg: dict(self.CONTEXT), explain=lambda *a: "Sepet düğmesi.", followup=followup)
		self.assertEqual(c.handle({"type": "followup", "query": "ne yapar?"})["status"], "info")  # nothing to follow up yet
		c.handle({"type": "explain", "elementId": "e_7"})
		self.assertEqual(c.handle({"type": "followup", "query": " ne yapar? "}), {"status": "explained", "text": "Cevap 1"})
		c.handle({"type": "followup", "query": "emin misin?"})
		data, shot, task, turns, question = calls[-1]
		self.assertEqual((set(data), shot, task, question), ({"page", "element"}, "shot", "explain", "emin misin?"))
		self.assertEqual(turns, [(None, "Sepet düğmesi."), ("ne yapar?", "Cevap 1")])

	def test_followup_expires(self):
		c = Coordinator(lambda msg: dict(self.CONTEXT), explain=lambda *a: "x", followup=lambda *a: "y")
		c.handle({"type": "explain", "elementId": "e_7"})
		with mock.patch.object(host.time, "monotonic", return_value=c.last["at"] + host.FOLLOWUP_TTL_S + 1):
			self.assertEqual(c.handle({"type": "followup", "query": "?"})["status"], "info")
		for bad in ["", "  ", "x" * 301, None]:
			self.assertEqual(c.handle({"type": "followup", "query": bad})["status"], "error")

	def test_request_alternates_turns_and_marks_questions(self):
		c = client_returning("Tamam.")
		llm.followup(c, {"page": PAGE}, None, "summarize", [("sepet", "Sepete gittim."), ("neden?", "Çünkü.")], "başka?")
		req = c.calls[0]
		self.assertTrue(req["system"].endswith(llm.FOLLOWUP))
		roles = [m["role"] for m in req["messages"]]
		self.assertEqual(roles, ["user", "assistant", "user", "assistant", "user"])
		self.assertIn("<user_request>\nsepet\n</user_request>", req["messages"][0]["content"][-1]["text"])
		self.assertEqual(req["messages"][-1]["content"], "<user_request>\nbaşka?\n</user_request>")


class TableTest(unittest.TestCase):
	def test_no_table_is_said_without_the_model(self):
		ext = FakeExtension({"table": {"page": PAGE, "table": None}})
		r = Coordinator(ext.ask, explain=lambda *a: self.fail("model called")).handle({"type": "table", "elementId": "e_2"})
		self.assertEqual(r["status"], "info")
		self.assertEqual(ext.sent, [{"type": "table", "elementId": "e_2"}])

	def test_table_reaches_the_model_redacted(self):
		table = {"caption": "Kartlar", "rows": [{"cells": ["4111 1111 1111 1111", "Visa"]}], "rowCount": 1, "columnCount": 2, "target": None}
		ext = FakeExtension({"table": {"page": PAGE, "table": table, "screenshot": "shot"}})
		seen = {}
		c = Coordinator(ext.ask, explain=lambda data, shot, task: seen.update(data=data, task=task) or "Kart tablosu.")
		self.assertEqual(c.handle({"type": "table", "elementId": "e_2"}), {"status": "explained", "text": "Kart tablosu."})
		self.assertEqual((set(seen["data"]), seen["task"]), ({"page", "table"}, "table"))
		self.assertNotIn("4111", json.dumps(seen["data"]))


class ChartTest(unittest.TestCase):
	def test_no_chart_is_said_without_the_model(self):
		ext = FakeExtension({"chart": {"page": PAGE, "chart": None}})
		r = Coordinator(ext.ask, explain=lambda *a: self.fail("model called")).handle({"type": "chart", "elementId": "e_3"})
		self.assertEqual((r["status"], r["code"]), ("info", "no_chart"))

	def test_chart_reaches_the_model(self):
		chart = {"title": "Satış", "texts": [{"text": "Ocak", "at": [0, 0, 1, 1]}], "marks": [], "markCount": 0}
		ext = FakeExtension({"chart": {"page": PAGE, "chart": chart}})
		seen = {}
		c = Coordinator(ext.ask, explain=lambda data, shot, task: seen.update(data=data, task=task) or "Bir çubuk grafik.")
		self.assertEqual(c.handle({"type": "chart", "elementId": "e_3"})["text"], "Bir çubuk grafik.")
		self.assertEqual((set(seen["data"]), seen["task"]), ({"page", "chart"}, "chart"))
		self.assertIn("approximate", llm.build_request({}, None, "chart")["system"])


class ReportTest(unittest.TestCase):
	def test_report_is_not_streamed_and_carries_the_page_address(self):
		ctx = {"page": PAGE, "element": {"tag": "div"}, "url": "https://shop.example/odeme/4111111111111111", "screenshot": None}
		holder, seen = {}, {}

		def explain(data, shot, task):
			seen.update(data=data, task=task, emit=holder["c"]._emit)
			return "AI ile yazıldı.\nWCAG 4.1.2"

		c = holder["c"] = Coordinator(lambda msg: dict(ctx), explain=explain)
		emitted = []
		r = c.handle({"type": "report", "elementId": "e_4"}, emitted.append)
		self.assertEqual(r["status"], "report")
		self.assertTrue(r["text"].startswith("https://shop.example/odeme/[kart numarası gizlendi]\n\n"))
		self.assertEqual((seen["task"], seen["emit"], emitted), ("report", None, []))
		self.assertNotIn("url", seen["data"])  # the address is for the header only

	def test_foreign_address_falls_back_to_the_origin(self):
		ctx = {"page": PAGE, "element": {"tag": "div"}, "url": "https://evil.example/x"}
		r = Coordinator(lambda msg: dict(ctx), explain=lambda *a: "Rapor").handle({"type": "report", "elementId": "e_4"})
		self.assertTrue(r["text"].startswith("https://shop.example\n\n"))


class CacheTest(unittest.TestCase):
	def test_same_element_is_answered_once_until_it_expires(self):
		ctx = {"page": PAGE, "element": {"tag": "div", "states": {"expanded": "false"}}, "screenshot": "shot"}
		calls = []
		c = Coordinator(lambda msg: json.loads(json.dumps(ctx)), explain=lambda *a: calls.append(a) or f"Cevap {len(calls)}")
		self.assertEqual(c.handle({"type": "explain", "elementId": "e_1"})["text"], "Cevap 1")
		self.assertEqual(c.handle({"type": "explain", "elementId": "e_1"})["text"], "Cevap 1")
		ctx["element"]["states"]["expanded"] = "true"  # changed state is a new question
		self.assertEqual(c.handle({"type": "explain", "elementId": "e_1"})["text"], "Cevap 2")
		later = time_after(host.CACHE_TTL_S + 1)
		with mock.patch.object(host.time, "monotonic", return_value=later):
			self.assertEqual(c.handle({"type": "explain", "elementId": "e_1"})["text"], "Cevap 3")

	def test_page_level_answers_are_not_cached(self):
		ctx = {"page": PAGE, "outline": {"mainText": "x"}}
		calls = []
		c = Coordinator(lambda msg: dict(ctx), explain=lambda *a: calls.append(a) or "Özet")
		c.handle({"type": "summarize"})
		c.handle({"type": "summarize"})
		self.assertEqual(len(calls), 2)


def time_after(seconds):
	import time

	return time.monotonic() + seconds


if __name__ == "__main__":
	unittest.main()
