"""Chrome Native Messaging framing: 4-byte little-endian length + UTF-8 JSON."""

import json
import struct


def read_message(stream):
	"""Return the next message, or None when Chrome closed the pipe."""
	header = stream.read(4)
	if len(header) < 4:
		return None
	(length,) = struct.unpack("<I", header)
	data = stream.read(length)
	if len(data) < length:
		return None
	return json.loads(data.decode("utf-8"))


def write_message(stream, msg):
	data = json.dumps(msg).encode("utf-8")
	stream.write(struct.pack("<I", len(data)) + data)
	stream.flush()
