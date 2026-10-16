"""Map NVDA's navigator object to an element ID from the extension snapshot.

Order (see docs/spike-dom-mapping.md): temporary marker class, unique HTML id, bounding box.
Every match must agree with the navigator's tag and overlap its rect, so a page cannot
redirect grounding by forging ids or marker classes on unrelated elements.
"""

from dataclasses import dataclass, field

# shortcut: threshold chosen by reasoning (1px rounding on a 16px box ~ 0.78), recalibrate from spike logs.
RECT_MATCH_IOU = 0.8
MARKER_PREFIX = "nvai-"


@dataclass
class Match:
	status: str  # "matched" | "ambiguous" | "none"
	element_id: str | None = None
	method: str | None = None  # "marker" | "html-id" | "rect"
	candidates: list[str] = field(default_factory=list)


def css_rect(screen_rect, viewport_origin, dpr):
	"""NVDA physical screen rect -> CSS px relative to the viewport (getBoundingClientRect space)."""
	x, y, w, h = screen_rect
	ox, oy = viewport_origin
	return ((x - ox) / dpr, (y - oy) / dpr, w / dpr, h / dpr)


def iou(a, b):
	w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
	h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
	inter = w * h if w > 0 and h > 0 else 0
	union = a[2] * a[3] + b[2] * b[3] - inter
	return inter / union if union > 0 else 0.0


def resolve(nav, elements, dpr, nonce=None):
	"""Pick the snapshot element NVDA's navigator object refers to.

	nav: {"tag", "htmlId", "classes", "screenRect", "viewportOrigin"} from the NVDA add-on.
	elements: [{"id", "tag", "htmlId", "rect"}] from the extension snapshot, rect in CSS px.
	nonce: marker nonce of the current marking round, or None if no markers were applied.
	"""
	rect = None
	if nav.get("screenRect") and nav.get("viewportOrigin"):
		rect = css_rect(nav["screenRect"], nav["viewportOrigin"], dpr)
	tag = nav.get("tag")

	def tag_ok(el):
		return not tag or el["tag"] == tag

	def plausible(el):
		if not tag_ok(el):
			return False
		return rect is None or rect[2] * rect[3] == 0 or iou(rect, el["rect"]) > 0

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

	if rect is None:
		return Match("none")
	hits = [el["id"] for el in elements if tag_ok(el) and iou(rect, el["rect"]) >= RECT_MATCH_IOU]
	if len(hits) == 1:
		return Match("matched", hits[0], "rect")
	if hits:
		return Match("ambiguous", candidates=hits)
	return Match("none")
