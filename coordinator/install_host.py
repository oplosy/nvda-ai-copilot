"""Register the coordinator as a Chrome, Edge and Firefox native messaging host for the current user.

Usage: python install_host.py [extension-id]
       python install_host.py --uninstall
The default IDs are the dev ID (from the public "key" in extension/manifest.json) and the store IDs.

nvda-addon/build.py copies this file into the add-on, which registers the coordinator it ships
(register/registered_manifest/unregister). Standard library only.
"""

import json
import re
import sys
import winreg
from pathlib import Path

HOST = "com.nvda_ai_copilot.coordinator"
# Dev builds load unpacked with the pinned key. Chrome Web Store and Edge Add-ons assign their own
# IDs on first submission; add them here so the store builds may connect too.
EXTENSION_IDS = ("ijifaphfddholfknhblhfnoajaekjgnj",)
EXTENSION_ID = EXTENSION_IDS[0]

# Edge reads its own key; both point at the same manifest.
REG_KEYS = [
	rf"Software\Google\Chrome\NativeMessagingHosts\{HOST}",
	rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST}",
]
# Firefox names extensions by the gecko ID in extension/manifest.json and needs its own manifest:
# "allowed_extensions" instead of Chrome's "allowed_origins".
FIREFOX_ID = "nvda-ai-copilot@oplosy"
FIREFOX_REG_KEY = rf"Software\Mozilla\NativeMessagingHosts\{HOST}"


def _write_manifest(path, app_dir, allowed):
	path.write_text(
		json.dumps(
			{"name": HOST, "description": "NVDA AI Copilot coordinator", "path": str(app_dir / "run_host.bat"), "type": "stdio", **allowed},
			indent=2,
		),
		encoding="utf-8",
	)


def register(app_dir, ext_ids=EXTENSION_IDS):
	"""Writes the host manifests into app_dir (next to run_host.bat) and points Chrome, Edge and
	Firefox at them. Returns the Chrome and Edge manifest path."""
	app_dir = Path(app_dir)
	if not ext_ids or not all(re.fullmatch(r"[a-p]{32}", i) for i in ext_ids):
		raise ValueError(f"invalid extension IDs: {ext_ids}")
	manifest_path = app_dir / f"{HOST}.json"
	_write_manifest(manifest_path, app_dir, {"allowed_origins": [f"chrome-extension://{i}/" for i in ext_ids]})
	firefox_path = app_dir / f"{HOST}.firefox.json"
	_write_manifest(firefox_path, app_dir, {"allowed_extensions": [FIREFOX_ID]})
	for key in REG_KEYS:
		winreg.SetValue(winreg.HKEY_CURRENT_USER, key, winreg.REG_SZ, str(manifest_path))
	winreg.SetValue(winreg.HKEY_CURRENT_USER, FIREFOX_REG_KEY, winreg.REG_SZ, str(firefox_path))
	return manifest_path


def registered_manifest():
	"""The Chrome and Edge manifest path, or None if any browser is not registered, they disagree,
	or Firefox does not point at the manifest next to it."""
	paths = set()
	try:
		for key in REG_KEYS:
			paths.add(winreg.QueryValue(winreg.HKEY_CURRENT_USER, key))
		firefox = Path(winreg.QueryValue(winreg.HKEY_CURRENT_USER, FIREFOX_REG_KEY))
	except FileNotFoundError:
		return None
	if len(paths) != 1:
		return None
	path = Path(paths.pop())
	return path if firefox == path.with_name(f"{HOST}.firefox.json") else None


def unregister():
	for key in [*REG_KEYS, FIREFOX_REG_KEY]:
		try:
			winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
		except FileNotFoundError:
			pass


def main():
	here = Path(__file__).resolve().parent
	if sys.argv[1:] == ["--uninstall"]:
		unregister()
		(here / f"{HOST}.json").unlink(missing_ok=True)
		(here / f"{HOST}.firefox.json").unlink(missing_ok=True)
		print(f"Unregistered {HOST}")
		return
	if len(sys.argv) > 2 or (len(sys.argv) == 2 and not re.fullmatch(r"[a-p]{32}", sys.argv[1])):
		sys.exit("usage: python install_host.py [32-char extension id from chrome://extensions] | --uninstall")
	ext_ids = (sys.argv[1],) if len(sys.argv) == 2 else EXTENSION_IDS
	manifest_path = register(here, ext_ids)
	print(f"Registered {HOST} for {', '.join(ext_ids)} and Firefox ({FIREFOX_ID}) -> {manifest_path}")


if __name__ == "__main__":
	main()
