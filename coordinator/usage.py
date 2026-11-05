"""Claude usage per calendar month and its estimated cost, so the person can see what Copilot
costs them and set a monthly limit.

Only counts and amounts are stored, never what was asked or answered. The file is read again
before every write, so two coordinators (two browser profiles) add up instead of overwriting.
Standard library only: the NVDA add-on copies this module to read the same file.
"""

import json
import math
import os
import time

# US dollars per million tokens (Anthropic API list prices): input, output, cache read.
# Cache writes cost 1.25 times the input price.
PRICES = {
	"claude-haiku-5-5": (0.10, 0.50, 0.01),
	"claude-sonnet-5-5": (2.00, 10.00, 0.20),
	"claude-opus-5-5": (4.00, 20.00, 0.20),
}
# Haiku 5.5 prompts over 100K tokens are billed at a higher rate.
LONG_PROMPT = {"claude-haiku-5-5": (100_000, (0.50, 2.50, 0.05))}
CACHE_WRITE = 1.25
MONTHS_KEPT = 12
FIELDS = ("requests", "inputTokens", "outputTokens", "costUsd")


def _count(value):
	return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def cost(model, usage):
	"""Estimated US dollars for one response's usage, or None if the model has no known price."""
	if model not in PRICES:
		return None
	fresh = _count(getattr(usage, "input_tokens", 0))
	written = _count(getattr(usage, "cache_creation_input_tokens", 0))
	read = _count(getattr(usage, "cache_read_input_tokens", 0))
	output = _count(getattr(usage, "output_tokens", 0))
	price_in, price_out, price_read = PRICES[model]
	long_prompt = LONG_PROMPT.get(model)
	if long_prompt and fresh + written + read > long_prompt[0]:
		price_in, price_out, price_read = long_prompt[1]
	return (fresh * price_in + written * price_in * CACHE_WRITE + read * price_read + output * price_out) / 1_000_000


def _valid_month(entry):
	if not isinstance(entry, dict):
		return False
	numbers = [entry.get(k) for k in FIELDS]
	return all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and n >= 0 for n in numbers)


class Usage:
	"""{"YYYY-MM": {"requests", "inputTokens", "outputTokens", "costUsd"}}; path None keeps it in memory."""

	def __init__(self, path=None, clock=time.time):
		self.path = path
		self.clock = clock
		self.data = {}

	def _key(self):
		return time.strftime("%Y-%m", time.localtime(self.clock()))

	def _load(self):
		if not self.path:
			return
		try:
			loaded = json.loads(self.path.read_text(encoding="utf-8"))
		except (OSError, ValueError):
			loaded = {}  # missing or unreadable: start empty rather than refuse to work
		self.data = {k: v for k, v in loaded.items() if _valid_month(v)} if isinstance(loaded, dict) else {}

	def month(self):
		"""This month's totals."""
		self._load()
		key = self._key()
		entry = self.data.get(key) or dict.fromkeys(FIELDS, 0)
		return {"month": key, **{k: entry[k] for k in FIELDS}}

	def record(self, served_model, requested_model, usage):
		"""Adds one response. A fallback model without a known price is priced as the requested one."""
		amount = cost(served_model, usage)
		if amount is None:
			amount = cost(requested_model, usage) or 0.0
		self._load()
		key = self._key()
		entry = self.data.setdefault(key, dict.fromkeys(FIELDS, 0))
		entry["requests"] += 1
		entry["inputTokens"] += sum(
			_count(getattr(usage, f, 0)) for f in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
		)
		entry["outputTokens"] += _count(getattr(usage, "output_tokens", 0))
		entry["costUsd"] += amount
		for old in sorted(self.data)[:-MONTHS_KEPT]:
			del self.data[old]
		self._write()
		return amount

	def _write(self):
		if not self.path:
			return
		self.path.parent.mkdir(parents=True, exist_ok=True)
		tmp = self.path.with_suffix(".tmp")
		tmp.write_text(json.dumps(self.data, sort_keys=True), encoding="utf-8")
		os.replace(tmp, self.path)  # never leave a half-written file behind
