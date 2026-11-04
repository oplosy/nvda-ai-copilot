"""Installs the coordinator shipped inside the add-on and keeps the browsers pointed at it.

Chrome keeps the coordinator running while the extension is connected, which locks its files, and
NVDA replaces the add-on folder on update. So the add-on's copy is never run in place: each version
is copied to its own folder under INSTALL_ROOT and the native host registration moves to it. Folders
of other versions (and the layout of the old install.bat) are removed once nothing holds them.

Standard library only and no NVDA imports, so test_bundle.py can run it outside NVDA.
"""

import os
import re
import shutil
from pathlib import Path

INSTALL_ROOT = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "nvda-ai-copilot"
# What install.bat put straight into INSTALL_ROOT before versions had their own folders.
LEGACY_NAMES = ("python", "app", "site-packages", "install.bat", "uninstall.bat")
_VERSION = re.compile(r"[0-9][0-9A-Za-z.+-]*")


def ensure_installed(bundle_dir, version, register, registered_manifest, root=INSTALL_ROOT):
	"""Copies bundle_dir to root/<version> if missing and registers it.

	register(app_dir) and registered_manifest() are install_host's functions (injected for tests).
	Returns the app folder the browsers now use, or None if the add-on carries no coordinator.
	"""
	bundle_dir, root = Path(bundle_dir), Path(root)
	if not (bundle_dir / "app" / "run_host.bat").is_file():
		return None
	if not _VERSION.fullmatch(version):
		raise ValueError(f"unexpected add-on version: {version!r}")
	target = root / version
	if not target.is_dir():
		root.mkdir(parents=True, exist_ok=True)
		staging = root / f".{version}.partial"
		shutil.rmtree(_long(staging), ignore_errors=True)
		shutil.copytree(_long(bundle_dir), _long(staging))
		os.replace(_long(staging), _long(target))  # a version folder only ever appears complete
	app_dir = target / "app"
	manifest = app_dir / "com.nvda_ai_copilot.coordinator.json"
	current = registered_manifest()
	if current is None or Path(current) != manifest or not manifest.is_file():
		register(app_dir)
	remove_old(root, keep=version)
	return app_dir


def _long(path):
	"""Extended-length form, so a long user folder name cannot push a package file past MAX_PATH while copying."""
	path = str(Path(path).resolve())
	return path if os.name != "nt" or path.startswith("\\\\?\\") else "\\\\?\\" + path


def remove_old(root, keep):
	"""Best effort: a folder the running coordinator still holds is left for the next start."""
	root = Path(root)
	if not root.is_dir():
		return
	for entry in root.iterdir():
		if entry.name == keep:
			continue
		if not (_VERSION.fullmatch(entry.name) or entry.name in LEGACY_NAMES or entry.name.endswith(".partial")):
			continue
		try:
			if entry.is_dir():
				shutil.rmtree(_long(entry))
			else:
				entry.unlink()
		except OSError:
			pass
