"""Tests for globalPlugins/nvdaAiCopilot/bundle.py. Run: coordinator\\.venv\\Scripts\\python -m unittest discover -s nvda-addon"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("bundle", Path(__file__).parent / "globalPlugins" / "nvdaAiCopilot" / "bundle.py")
assert _spec and _spec.loader
bundle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bundle)

MANIFEST = "com.nvda_ai_copilot.coordinator.json"


class FakeRegistry:
	def __init__(self, current=None):
		self.current = current
		self.calls = []

	def register(self, app_dir):
		self.calls.append(Path(app_dir))
		(Path(app_dir) / MANIFEST).write_text("{}", encoding="utf-8")
		self.current = Path(app_dir) / MANIFEST

	def registered_manifest(self):
		return self.current


class EnsureInstalledTest(unittest.TestCase):
	def setUp(self):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		self.base = Path(tmp.name)
		self.bundle = self.base / "addon" / "coordinator"
		(self.bundle / "app").mkdir(parents=True)
		(self.bundle / "app" / "run_host.bat").write_text("@echo off", encoding="utf-8")
		(self.bundle / "python").mkdir()
		(self.bundle / "python" / "python.exe").write_bytes(b"MZ")
		self.root = self.base / "Programs" / "nvda-ai-copilot"

	def install(self, version, reg):
		return bundle.ensure_installed(self.bundle, version, reg.register, reg.registered_manifest, root=self.root)

	def test_first_start_copies_and_registers(self):
		reg = FakeRegistry()
		app = self.install("0.3.0", reg)
		self.assertEqual(app, self.root / "0.3.0" / "app")
		self.assertTrue((self.root / "0.3.0" / "python" / "python.exe").is_file())
		self.assertEqual(reg.calls, [app])

	def test_next_start_changes_nothing(self):
		reg = FakeRegistry()
		self.install("0.3.0", reg)
		marker = self.root / "0.3.0" / "python" / "python.exe"
		marker.write_bytes(b"changed")
		self.install("0.3.0", reg)
		self.assertEqual(marker.read_bytes(), b"changed")
		self.assertEqual(len(reg.calls), 1)

	def test_registration_lost_or_elsewhere_is_restored(self):
		reg = FakeRegistry()
		self.install("0.3.0", reg)
		reg.current = None
		self.install("0.3.0", reg)
		reg.current = self.base / "dev" / MANIFEST
		self.install("0.3.0", reg)
		self.assertEqual(len(reg.calls), 3)

	def test_deleted_manifest_is_rewritten(self):
		reg = FakeRegistry()
		app = self.install("0.3.0", reg)
		(app / MANIFEST).unlink()
		self.install("0.3.0", reg)
		self.assertTrue((app / MANIFEST).is_file())

	def test_update_moves_registration_and_removes_old_and_legacy(self):
		reg = FakeRegistry()
		self.install("0.3.0", reg)
		for name in ("app", "python"):
			(self.root / name).mkdir()
		(self.root / "install.bat").write_text("", encoding="utf-8")
		(self.root / ".0.4.0.partial").mkdir()
		(self.root / "notes").mkdir()  # not ours: left alone
		app = self.install("0.4.0", reg)
		self.assertEqual(reg.current, app / MANIFEST)
		self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["0.4.0", "notes"])

	def test_locked_old_folder_is_left_for_later(self):
		reg = FakeRegistry()
		self.install("0.3.0", reg)
		original = bundle.shutil.rmtree

		def locked(path, *args, **kwargs):
			if Path(path).name == "0.3.0":
				raise PermissionError("in use")
			return original(path, *args, **kwargs)

		bundle.shutil.rmtree = locked
		try:
			self.install("0.4.0", reg)
		finally:
			bundle.shutil.rmtree = original
		self.assertTrue((self.root / "0.3.0").is_dir())
		self.install("0.4.0", reg)
		self.assertFalse((self.root / "0.3.0").exists())

	def test_dev_build_without_coordinator_does_nothing(self):
		reg = FakeRegistry()
		empty = self.base / "dev-addon" / "coordinator"
		self.assertIsNone(bundle.ensure_installed(empty, "0.3.0", reg.register, reg.registered_manifest, root=self.root))
		self.assertFalse(self.root.exists())
		self.assertEqual(reg.calls, [])

	def test_version_cannot_escape_the_install_folder(self):
		reg = FakeRegistry()
		for bad in ("..", "../x", "a\\b", ""):
			with self.assertRaises(ValueError):
				self.install(bad, reg)


if __name__ == "__main__":
	unittest.main()
