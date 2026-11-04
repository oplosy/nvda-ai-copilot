"""Build dist/nvda-ai-copilot-extension-<version>.zip for the Chrome Web Store and Edge Add-ons.

The store assigns its own ID, so the dev "key" is left out of the manifest; add the store IDs to
EXTENSION_IDS in coordinator/install_host.py. Tests and anything the manifest does not load stay out.
Stops if the extension and the NVDA add-on versions differ. Standard library only.
"""

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"


def loaded_files(manifest):
	files = [manifest["background"]["service_worker"]]
	for cs in manifest.get("content_scripts", []):
		files += cs.get("js", []) + cs.get("css", [])
	files += list(manifest.get("icons", {}).values())
	return list(dict.fromkeys(files))


def main():
	manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
	addon_version = re.search(r"^version = (\S+)$", (ROOT / "nvda-addon" / "manifest.ini").read_text(encoding="utf-8"), re.M)
	if not addon_version or addon_version.group(1) != manifest["version"]:
		sys.exit(f"extension version {manifest['version']} differs from the NVDA add-on's ({addon_version and addon_version.group(1)})")
	manifest.pop("key", None)
	files = loaded_files(manifest)
	missing = [f for f in files if not (EXT / f).is_file()]
	if missing:
		sys.exit(f"manifest names missing files: {missing}")
	out = ROOT / "dist" / f"nvda-ai-copilot-extension-{manifest['version']}.zip"
	out.parent.mkdir(exist_ok=True)
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
		z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
		for name in files:
			z.write(EXT / name, name)
	print(out)


if __name__ == "__main__":
	main()
