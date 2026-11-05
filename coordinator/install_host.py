"""Register the coordinator as a Chrome and Edge native messaging host for the current user.

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


def register(app_dir, ext_ids=EXTENSION_IDS):
	"""Writes the host manifest into app_dir (next to run_host.bat) and points both browsers at it."""
	app_dir = Path(app_dir)
	if not ext_ids or not all(re.fullmatch(r"[a-p]{32}", i) for i in ext_ids):
		raise ValueError(f"invalid extension IDs: {ext_ids}")
	manifest_path = app_dir / f"{HOST}.json"
	manifest_path.write_text(
		json.dumps(
			{
				"name": HOST,
				"description": "NVDA AI Copilot coordinator",
				"path": str(app_dir / "run_host.bat"),
				"type": "stdio",
				"allowed_origins": [f"chrome-extension://{i}/" for i in ext_ids],
			},
			indent=2,
		),
		encoding="utf-8",
	)
	for key in REG_KEYS:
		winreg.SetValue(winreg.HKEY_CURRENT_USER, key, winreg.REG_SZ, str(manifest_path))
	return manifest_path


def registered_manifest():
	"""The manifest path both browsers use, or None if they are not registered or disagree."""
	paths = set()
	for key in REG_KEYS:
		try:
			paths.add(winreg.QueryValue(winreg.HKEY_CURRENT_USER, key))
		except FileNotFoundError:
			return None
	return Path(paths.pop()) if len(paths) == 1 else None


def unregister():
	for key in REG_KEYS:
		try:
			winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
		except FileNotFoundError:
			pass


def main():
	here = Path(__file__).resolve().parent
	if sys.argv[1:] == ["--uninstall"]:
		unregister()
		(here / f"{HOST}.json").unlink(missing_ok=True)
		print(f"Unregistered {HOST}")
		return
	if len(sys.argv) > 2 or (len(sys.argv) == 2 and not re.fullmatch(r"[a-p]{32}", sys.argv[1])):
		sys.exit("usage: python install_host.py [32-char extension id from chrome://extensions] | --uninstall")
	ext_ids = (sys.argv[1],) if len(sys.argv) == 2 else EXTENSION_IDS
	manifest_path = register(here, ext_ids)
	print(f"Registered {HOST} for {', '.join(ext_ids)} -> {manifest_path}")


if __name__ == "__main__":
	main()
