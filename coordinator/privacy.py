"""Last line of defense before page data leaves the machine.

The extension never reads field values; this drops any that slip through and masks
card numbers that appear as page text.
"""

import re

CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
CARD_MASK = "[kart numarası gizlendi]"
DROP_KEYS = {"value", "defaultValue"}


def _luhn_ok(digits):
	total = 0
	for i, ch in enumerate(reversed(digits)):
		d = int(ch)
		if i % 2:
			d = d * 2 - 9 if d > 4 else d * 2
		total += d
	return total % 10 == 0


def mask_cards(text):
	def repl(m):
		digits = re.sub(r"\D", "", m.group())
		return CARD_MASK if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group()

	return CARD_CANDIDATE.sub(repl, text)


def redact(data):
	"""Copy of data with value fields dropped and card numbers masked in every string."""
	if isinstance(data, dict):
		return {k: redact(v) for k, v in data.items() if k not in DROP_KEYS}
	if isinstance(data, list):
		return [redact(v) for v in data]
	if isinstance(data, str):
		return mask_cards(data)
	return data
