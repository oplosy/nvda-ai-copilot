"""Map NVDA's navigator object to an element ID from the extension snapshot.

Order (see docs/spike-dom-mapping.md): temporary marker class, unique HTML id, bounding box.
Every match must agree with the navigator's tag and overlap its rect, so a page cannot
redirect grounding by forging ids or marker classes on unrelated elements.

Calibration (docs/spike-dom-mapping.md, "Results"): the IA2 document root sits at the viewport
origin even when scrolled, and Chromium reports the enclosing integer rect of the element in
physical pixels. Comparing in that space makes a true match IoU 1.0 even for small icons.
"""

import math
from dataclasses import dataclass, field

# Exact matches score 1.0 after snapping; the margin covers zoom/DPI rounding differences.
RECT_MATCH_IOU = 0.9
MARKER_PREFIX = "nvai-"
_EPS = 1e-6


@dataclass
class Match:
	status: str  # "matched" | "ambiguous" | "none"
	element_id: str | None = None
	method: str | None = None  # "marker" | "html-id" | "rect"
	candidates: list[str] = field(default_factory=list)


def screen_rect(css_rect, viewport_origin, dpr):
	"""Extension CSS rect -> the enclosing physical-pixel screen rect Chromium gives NVDA."""
	x, y, w, h = css_rect
	ox, oy = viewport_origin
	left = math.floor(ox + x * dpr + _EPS)
	top = math.floor(oy + y * dpr + _EPS)
	right = math.ceil(ox + (x + w) * dpr - _EPS)
	bottom = math.ceil(oy + (y + h) * dpr - _EPS)
	return (left, top, right - left, bottom - top)


def iou(a, b):
	w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
	h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
	inter = w * h if w > 0 and h > 0 else 0
	union = a[2] * a[3] + b[2] * b[3] - inter
	return inter / union if union > 0 else 0.0


def resolve(nav, elements, dpr, nonce=None):
	"""Pick the snapshot element NVDA's navigator object refers to.

	nav: {"tag", "htmlId", "classes", "screenRect", "viewportOrigin"} from the NVDA add-on;
	screenRect is physical screen pixels, viewportOrigin the IA2 document root's position.
	elements: [{"id", "tag", "htmlId", "rect"}] from the extension snapshot, rect in CSS px.
	nonce: marker nonce of the current marking round, or None if no markers were applied.
	"""
	rect = nav.get("screenRect") if nav.get("viewportOrigin") else None
	origin = nav.get("viewportOrigin")
	tag = nav.get("tag")

	def overlap(el):
		return iou(rect, screen_rect(el["rect"], origin, dpr))

	def tag_ok(el):
		return not tag or el["tag"] == tag

	def plausible(el):
		if not tag_ok(el):
			return False
		return not rect or rect[2] * rect[3] == 0 or overlap(el) > 0

	if nonce:
		by_id = {el["id"]: el for el in elements}
		prefix = f"{MARKER_PREFIX}{nonce}-"
		for token in (nav.get("classes") or "").split():
			el = by_id.get(token[len(prefix):]) if token.startswith(prefix) else None
			if el and plausible(el):
				return Match("matched", el["id"], "marker")

	html_id = nav.get("htmlId")
	if html_id:
		same = [el for el in elements if el["htmlId"] == html_id]
		if len(same) == 1 and plausible(same[0]):
			return Match("matched", same[0]["id"], "html-id")

	if not rect:
		return Match("none")
	hits = [el["id"] for el in elements if tag_ok(el) and overlap(el) >= RECT_MATCH_IOU]
	if len(hits) == 1:
		return Match("matched", hits[0], "rect")
	if hits:
		return Match("ambiguous", candidates=hits)
	return Match("none")
