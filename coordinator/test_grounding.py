import unittest

from grounding import resolve, screen_rect

BUTTON = {"id": "e_1", "tag": "button", "htmlId": "go", "rect": (10, 10, 80, 30)}
LINK = {"id": "e_2", "tag": "a", "htmlId": None, "rect": (10, 100, 28, 18)}
SPAN = {"id": "e_3", "tag": "span", "htmlId": None, "rect": (10, 101, 28, 17)}
OUTER = {"id": "e_4", "tag": "div", "htmlId": None, "rect": (200, 10, 40, 40)}
INNER = {"id": "e_5", "tag": "div", "htmlId": None, "rect": (200, 10, 40, 40)}
ELEMENTS = [BUTTON, LINK, SPAN, OUTER, INNER]


def nav(css, tag, html_id=None, classes=None, origin=(100, 200), dpr=1.0):
	x, y, w, h = css
	return {
		"tag": tag,
		"htmlId": html_id,
		"classes": classes,
		"screenRect": (origin[0] + x * dpr, origin[1] + y * dpr, w * dpr, h * dpr),
		"viewportOrigin": origin,
	}


class ResolveTest(unittest.TestCase):
	def test_screen_rect_applies_origin_and_dpr(self):
		self.assertEqual(screen_rect((10, 10, 80, 30), (100, 200), 1.5), (115, 215, 120, 45))

	def test_screen_rect_matches_measured_chromium_rounding(self):
		# Measured in Chrome 155 via UIA (same bounds as IA2 accLocation), viewport origin (0, 87).
		self.assertEqual(screen_rect((200, 10.5, 16, 16), (0, 87), 1), (200, 97, 16, 17))
		self.assertEqual(screen_rect((300.390625, 20.59375, 33.296875, 17.6875), (0, 87), 1), (300, 107, 34, 19))
		self.assertEqual(screen_rect((200, -2939.5, 16, 16), (0, 87), 1), (200, -2853, 16, 17))  # scrolled

	def test_small_fractional_icon_still_matches(self):
		icon = {"id": "e_9", "tag": "div", "htmlId": None, "rect": (200, 10.5, 8, 8)}
		nav_icon = {"tag": "div", "htmlId": None, "classes": None, "screenRect": (200, 97, 8, 9), "viewportOrigin": (0, 87)}
		m = resolve(nav_icon, [icon, BUTTON], 1)
		self.assertEqual((m.status, m.element_id), ("matched", "e_9"))

	def test_unique_html_id(self):
		m = resolve(nav(BUTTON["rect"], "button", html_id="go"), ELEMENTS, 1.0)
		self.assertEqual((m.status, m.element_id, m.method), ("matched", "e_1", "html-id"))

	def test_duplicate_html_id_falls_back_to_rect(self):
		dup = {**OUTER, "htmlId": "go", "tag": "button"}
		m = resolve(nav(BUTTON["rect"], "button", html_id="go"), [BUTTON, dup], 1.0)
		self.assertEqual((m.element_id, m.method), ("e_1", "rect"))

	def test_rect_with_zoom(self):
		m = resolve(nav(LINK["rect"], "a", dpr=1.5), ELEMENTS, 1.5)
		self.assertEqual((m.status, m.element_id, m.method), ("matched", "e_2", "rect"))

	def test_nested_same_tag_is_ambiguous(self):
		m = resolve(nav(OUTER["rect"], "div"), ELEMENTS, 1.0)
		self.assertEqual((m.status, m.candidates), ("ambiguous", ["e_4", "e_5"]))

	def test_marker_breaks_ambiguity(self):
		m = resolve(nav(OUTER["rect"], "div", classes="x nvai-n1-e_5"), ELEMENTS, 1.0, nonce="n1")
		self.assertEqual((m.status, m.element_id, m.method), ("matched", "e_5", "marker"))

	def test_marker_with_wrong_nonce_is_ignored(self):
		m = resolve(nav(OUTER["rect"], "div", classes="nvai-old-e_5"), ELEMENTS, 1.0, nonce="n1")
		self.assertEqual(m.status, "ambiguous")

	def test_forged_marker_on_unrelated_element_is_rejected(self):
		# Navigator is on the link; a marker naming the button must not win.
		m = resolve(nav(LINK["rect"], "a", classes="nvai-n1-e_1"), ELEMENTS, 1.0, nonce="n1")
		self.assertEqual((m.element_id, m.method), ("e_2", "rect"))

	def test_no_overlap_is_none(self):
		self.assertEqual(resolve(nav((500, 500, 10, 10), "button"), ELEMENTS, 1.0).status, "none")

	def test_missing_rect_without_id_is_none(self):
		self.assertEqual(resolve({"tag": "div"}, ELEMENTS, 1.0).status, "none")


if __name__ == "__main__":
	unittest.main()
