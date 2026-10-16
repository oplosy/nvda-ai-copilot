"""Register the coordinator as a Chrome native messaging host for the current user.

Usage: python install_host.py [extension-id]
The default ID follows from the public "key" in extension/manifest.json.
"""

import json
import re
import sys
import winreg
from pathlib import Path

HOST = "com.nvda_ai_copilot.coordinator"
EXTENSION_ID = "ijifaphfddholfknhblhfnoajaekjgnj"


def main():
	ext_id = sys.argv[1] if len(sys.argv) > 1 else EXTENSION_ID
	if len(sys.argv) > 2 or not re.fullmatch(r"[a-p]{32}", ext_id):
		sys.exit("usage: python install_host.py [32-char extension id from chrome://extensions]")
	here = Path(__file__).resolve().parent
	manifest_path = here / f"{HOST}.json"
	manifest_path.write_text(
		json.dumps(
			{
				"name": HOST,
				"description": "NVDA AI Copilot coordinator",
				"path": str(here / "run_host.bat"),
				"type": "stdio",
				"allowed_origins": [f"chrome-extension://{ext_id}/"],
			},
			indent=2,
		),
		encoding="utf-8",
	)
	winreg.SetValue(
		winreg.HKEY_CURRENT_USER,
		rf"Software\Google\Chrome\NativeMessagingHosts\{HOST}",
		winreg.REG_SZ,
		str(manifest_path),
	)
	print(f"Registered {HOST} for {ext_id} -> {manifest_path}")


if __name__ == "__main__":
	main()
