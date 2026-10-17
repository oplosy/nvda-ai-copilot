"""Anthropic API key at rest, encrypted for the current Windows user with DPAPI.

The NVDA add-on saves it from its settings panel and the coordinator reads it. nvda-addon/build.py
copies this file into the add-on, so both sides share one implementation. Standard library only.
"""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

KEY_FILE = Path(os.environ["LOCALAPPDATA"]) / "nvda-ai-copilot" / "api-key.bin"
_ENTROPY = b"nvda-ai-copilot api key"
_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
	_fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_PROTO = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
for _fn in (_crypt32.CryptProtectData, _crypt32.CryptUnprotectData):
	_fn.argtypes = _PROTO
	_fn.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data):
	buf = ctypes.create_string_buffer(data, len(data))
	return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(fn, data):
	# The second values keep the buffers alive until the call returns.
	data_in, _ = _blob(data)
	entropy, __ = _blob(_ENTROPY)
	out = _Blob()
	if not fn(ctypes.byref(data_in), None, ctypes.byref(entropy), None, None, _UI_FORBIDDEN, ctypes.byref(out)):
		raise ctypes.WinError(ctypes.get_last_error())
	try:
		return ctypes.string_at(out.pbData, out.cbData)
	finally:
		_kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def valid_key(key):
	"""A key is one token of printable ASCII; anything else is a paste mistake."""
	return bool(key) and key.isascii() and key.isprintable() and " " not in key


def save_key(key):
	if not valid_key(key):
		raise ValueError("invalid API key")
	KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
	tmp = KEY_FILE.with_suffix(".tmp")
	tmp.write_bytes(_dpapi(_crypt32.CryptProtectData, key.encode("ascii")))
	os.replace(tmp, KEY_FILE)  # never leave a half-written key behind


def load_key():
	"""The saved key, or None if there is none. Raises OSError if it cannot be decrypted."""
	try:
		data = KEY_FILE.read_bytes()
	except FileNotFoundError:
		return None
	return _dpapi(_crypt32.CryptUnprotectData, data).decode("ascii")


def delete_key():
	KEY_FILE.unlink(missing_ok=True)


def has_key():
	return KEY_FILE.exists()
