"""Draw the extension icons and the store promo tile as PNG files.

  extension/icons/icon-{16,32,48,128}.png  rounded blue square, white speech bubble, blue sparkle
  docs/store/promo-440x280.png             the same bubble on a full blue tile

A speech bubble for the spoken answer, a sparkle for AI. Plain shapes, so they stay readable at
16 px. Standard library only: each pixel is supersampled (4x4) for smooth edges and written with zlib.
Run it again after changing the shapes; the PNGs are committed.
"""

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLUE = (27, 79, 156)
WHITE = (255, 255, 255)
SAMPLES = 4


def rounded_rect(x, y, left, top, right, bottom, radius):
	cx = min(max(x, left + radius), right - radius)
	cy = min(max(y, top + radius), bottom - radius)
	return left <= x <= right and top <= y <= bottom and (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def in_polygon(x, y, points):
	inside = False
	for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
		if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
			inside = not inside
	return inside


def sparkle(cx, cy, outer, inner):
	return [
		(cx + (outer if i % 2 == 0 else inner) * math.sin(i * math.pi / 4), cy - (outer if i % 2 == 0 else inner) * math.cos(i * math.pi / 4))
		for i in range(8)
	]


SPARKLE = sparkle(64, 55, 25, 7)
TAIL = [(36, 82), (60, 82), (32, 106)]


def bubble(x, y):
	"""Color of the bubble design at (x, y) in a 128-unit box, or None outside it."""
	if in_polygon(x, y, SPARKLE):
		return BLUE
	if rounded_rect(x, y, 18, 22, 110, 86, 18) or in_polygon(x, y, TAIL):
		return WHITE
	return None


def icon(x, y):
	if not rounded_rect(x, y, 0, 0, 128, 128, 26):
		return None
	return bubble(x, y) or BLUE


def render(width, height, color_at):
	"""RGBA rows; color_at(x, y) gets coordinates in pixel units."""
	rows = []
	for py in range(height):
		row = bytearray()
		for px in range(width):
			acc = [0, 0, 0, 0]
			for sy in range(SAMPLES):
				for sx in range(SAMPLES):
					c = color_at(px + (sx + 0.5) / SAMPLES, py + (sy + 0.5) / SAMPLES)
					if c:
						acc[0] += c[0]
						acc[1] += c[1]
						acc[2] += c[2]
						acc[3] += 1
			n = acc[3]
			row += bytes((acc[0] // n, acc[1] // n, acc[2] // n, round(255 * n / SAMPLES**2)) if n else (0, 0, 0, 0))
		rows.append(bytes(row))
	return rows


def write_png(path, width, height, rows):
	def chunk(kind, data):
		return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

	raw = b"".join(b"\x00" + r for r in rows)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_bytes(
		b"\x89PNG\r\n\x1a\n"
		+ chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
		+ chunk(b"IDAT", zlib.compress(raw, 9))
		+ chunk(b"IEND", b"")
	)
	print(path)


def main():
	for size in (16, 32, 48, 128):
		scale = 128 / size
		write_png(ROOT / "extension" / "icons" / f"icon-{size}.png", size, size, render(size, size, lambda x, y: icon(x * scale, y * scale)))
	# Promo tile: the bubble at 2x, centered.
	w, h, s = 440, 280, 2
	ox, oy = (w - 128 * s) / 2, (h - 128 * s) / 2 + 12
	write_png(ROOT / "docs" / "store" / "promo-440x280.png", w, h, render(w, h, lambda x, y: bubble((x - ox) / s, (y - oy) / s) or BLUE))


if __name__ == "__main__":
	main()
