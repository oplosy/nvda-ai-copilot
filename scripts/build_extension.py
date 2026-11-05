"""Build the store zips of the extension:

  dist/nvda-ai-copilot-extension-<version>.zip          Chrome Web Store and Edge Add-ons
  dist/nvda-ai-copilot-extension-firefox-<version>.zip  addons.mozilla.org (signing)

extension/manifest.json serves both browsers when loaded unpacked; each zip keeps only what its
browser reads. The Chrome stores assign their own ID, so the dev "key" is left out; add the store IDs
to EXTENSION_IDS in coordinator/install_host.py. Firefox keeps the gecko ID that install_host.py
allows. Tests and anything the manifest does not load stay out. Stops if the extension and the NVDA
add-on versions differ. Standard library only.
"""

import copy
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"


def chrome_manifest(manifest):
	"""Chrome and Edge run the background as a service worker and do not know Firefox's settings."""
	m = copy.deepcopy(manifest)
	m.pop("key", None)
	m.pop("browser_specific_settings", None)
	m["background"] = {"service_worker": m["background"]["service_worker"]}
	return m


def firefox_manifest(manifest):
	"""Firefox has no extension service workers; it loads the background scripts as an event page."""
	m = copy.deepcopy(manifest)
	m.pop("key", None)
	m["background"] = {"scripts": m["background"]["scripts"]}
	return m


def loaded_files(manifest):
	background = manifest["background"]
	files = [background["service_worker"]] if "service_worker" in background else list(background["scripts"])
	for cs in manifest.get("content_scripts", []):
		files += cs.get("js", []) + cs.get("css", [])
	files += list(manifest.get("icons", {}).values())
	return list(dict.fromkeys(files))


def write_zip(out, manifest):
	files = loaded_files(manifest)
	missing = [f for f in files if not (EXT / f).is_file()]
	if missing:
		sys.exit(f"manifest names missing files: {missing}")
	out.parent.mkdir(exist_ok=True)
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
		z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
		for name in files:
			z.write(EXT / name, name)
	print(out)


def main():
	manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
	addon_version = re.search(r"^version = (\S+)$", (ROOT / "nvda-addon" / "manifest.ini").read_text(encoding="utf-8"), re.M)
	if not addon_version or addon_version.group(1) != manifest["version"]:
		sys.exit(f"extension version {manifest['version']} differs from the NVDA add-on's ({addon_version and addon_version.group(1)})")
	version = manifest["version"]
	write_zip(ROOT / "dist" / f"nvda-ai-copilot-extension-{version}.zip", chrome_manifest(manifest))
	write_zip(ROOT / "dist" / f"nvda-ai-copilot-extension-firefox-{version}.zip", firefox_manifest(manifest))


if __name__ == "__main__":
	main()
