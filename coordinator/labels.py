"""AI explanations the person chose to keep, per site and element, spoken again on later visits.

An element is recognized by what identifies it across page loads (id, names, text, link, images,
the names of the fields next to it); states and surrounding text change too often to be part of it.
Stored as JSON in the user's data folder; only what the person saved, nothing else.
"""

import hashlib
import json
import os
import time

MAX_SAVED = 2000
IDENTITY_FIELDS = ("htmlId", "tag", "role", "type", "ariaLabel", "labelledBy", "title", "alt", "placeholder", "link", "labels", "text", "images")
# Fields that tell one element from another; tag, role and type alone match every similar control.
DISTINCTIVE = ("htmlId", "ariaLabel", "labelledBy", "title", "alt", "placeholder", "link", "labels", "text", "images")


def signature(element):
	"""Stable hash of an element description, or None if nothing in it is distinctive."""
	nearby = element.get("nearby") or {}
	identity = {k: element.get(k) for k in IDENTITY_FIELDS}
	identity["nearby"] = [nearby.get("before"), nearby.get("after")]
	if not any(identity[k] for k in DISTINCTIVE) and not any(identity["nearby"]):
		return None
	return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class SavedLabels:
	"""origin -> {signature: {"text", "saved"}}; path None keeps them in memory only."""

	def __init__(self, path=None):
		self.path = path
		self.data = {}
		if path:
			try:
				loaded = json.loads(path.read_text(encoding="utf-8"))
				self.data = loaded if isinstance(loaded, dict) else {}
			except (OSError, ValueError):
				pass  # missing or unreadable: start empty rather than refuse to work

	def get(self, origin, sig):
		entry = self.data.get(origin, {}).get(sig)
		return entry.get("text") if isinstance(entry, dict) else None

	def put(self, origin, sig, text):
		self.data.setdefault(origin, {})[sig] = {"text": text, "saved": time.time()}
		entries = [(e.get("saved", 0), o, s) for o, site in self.data.items() for s, e in site.items()]
		for _, o, s in sorted(entries)[: max(0, len(entries) - MAX_SAVED)]:
			del self.data[o][s]
		self._write()

	def delete(self, origin, sig):
		if self.data.get(origin, {}).pop(sig, None) is not None:
			self._write()

	def _write(self):
		if not self.path:
			return
		self.path.parent.mkdir(parents=True, exist_ok=True)
		tmp = self.path.with_suffix(".tmp")
		tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
		os.replace(tmp, self.path)  # never leave a half-written file behind
