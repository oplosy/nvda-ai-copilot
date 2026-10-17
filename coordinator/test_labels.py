import json
import tempfile
import unittest
from pathlib import Path

import labels
from host import Coordinator

PAGE = {"origin": "https://shop.example", "title": "Ürün"}
ICON_BUTTON = {"tag": "button", "htmlId": None, "text": "", "nearby": {"before": "Ürün ara", "after": "", "parent": "x"}, "states": {"expanded": None}}


class SignatureTest(unittest.TestCase):
	def test_states_and_surrounding_text_do_not_change_identity(self):
		changed = {**ICON_BUTTON, "nearby": {**ICON_BUTTON["nearby"], "parent": "y"}, "states": {"expanded": "true"}}
		self.assertEqual(labels.signature(ICON_BUTTON), labels.signature(changed))
		self.assertNotEqual(labels.signature(ICON_BUTTON), labels.signature({**ICON_BUTTON, "nearby": {"before": "E-posta"}}))

	def test_element_without_anything_distinctive_has_no_signature(self):
		self.assertIsNone(labels.signature({"tag": "div", "role": "button", "nearby": {"parent": "Fiyat 120 TL"}}))


class SavedLabelsTest(unittest.TestCase):
	def test_saved_labels_survive_a_restart_and_are_capped(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp) / "labels.json"
			store = labels.SavedLabels(path)
			store.put("https://a.example", "s1", "Arama düğmesi.")
			self.assertEqual(labels.SavedLabels(path).get("https://a.example", "s1"), "Arama düğmesi.")
			self.assertIsNone(labels.SavedLabels(path).get("https://b.example", "s1"))
			store.delete("https://a.example", "s1")
			self.assertIsNone(labels.SavedLabels(path).get("https://a.example", "s1"))
			path.write_text("not json")
			self.assertEqual(labels.SavedLabels(path).data, {})
		old_max, labels.MAX_SAVED = labels.MAX_SAVED, 2
		try:
			store = labels.SavedLabels()
			for i in range(3):
				store.put("https://a.example", f"s{i}", str(i))
			self.assertEqual(sorted(store.data["https://a.example"]), ["s1", "s2"])  # oldest dropped
		finally:
			labels.MAX_SAVED = old_max


class LabelFlowTest(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.ctx = {"page": PAGE, "element": ICON_BUTTON, "screenshot": None}
		self.c = Coordinator(lambda msg: json.loads(json.dumps(self.ctx)), explain=lambda *a: self.calls.append(a) or "Arama düğmesi.")

	def explain(self):
		return self.c.handle({"type": "explain", "elementId": "e_1"})

	def test_save_then_reuse_then_delete(self):
		self.assertEqual(self.c.handle({"type": "label"})["code"], "no_label")
		self.explain()
		self.assertEqual(self.c.handle({"type": "label"})["code"], "label_saved")
		self.c.cache.clear()  # a later visit: only the saved label can answer without the model
		r = self.explain()
		self.assertEqual((r["text"], r.get("saved"), len(self.calls)), ("Arama düğmesi.", True, 1))
		self.assertEqual(self.c.handle({"type": "label"})["code"], "label_deleted")
		self.c.cache.clear()
		self.assertNotIn("saved", self.explain())
		self.assertEqual(len(self.calls), 2)

	def test_unidentifiable_element_is_not_saved(self):
		self.ctx["element"] = {"tag": "div", "nearby": {}}
		self.explain()
		self.assertEqual(self.c.handle({"type": "label"})["code"], "label_unidentifiable")


if __name__ == "__main__":
	unittest.main()
