import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install_host


class FakeWinreg:
	HKEY_CURRENT_USER = object()
	REG_SZ = 1

	def __init__(self):
		self.values = {}

	def SetValue(self, root, key, kind, value):
		self.values[key] = value

	def QueryValue(self, root, key):
		if key not in self.values:
			raise FileNotFoundError(key)
		return self.values[key]

	def DeleteKey(self, root, key):
		if key not in self.values:
			raise FileNotFoundError(key)
		del self.values[key]


class InstallHostTest(unittest.TestCase):
	def setUp(self):
		self.reg = FakeWinreg()
		patcher = mock.patch.object(install_host, "winreg", self.reg)
		patcher.start()
		self.addCleanup(patcher.stop)
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		self.app = Path(tmp.name)

	def test_register_writes_manifest_for_every_id_and_both_browsers(self):
		ids = ("a" * 32, "b" * 32)
		path = install_host.register(self.app, ids)
		manifest = json.loads(path.read_text(encoding="utf-8"))
		self.assertEqual(manifest["path"], str(self.app / "run_host.bat"))
		self.assertEqual(manifest["allowed_origins"], [f"chrome-extension://{i}/" for i in ids])
		self.assertEqual(set(self.reg.values), set(install_host.REG_KEYS))
		self.assertEqual(install_host.registered_manifest(), path)

	def test_register_rejects_bad_ids(self):
		for ids in ((), ("not-an-id",), ("a" * 31,)):
			with self.assertRaises(ValueError):
				install_host.register(self.app, ids)
		self.assertEqual(self.reg.values, {})

	def test_registered_manifest_needs_both_browsers_to_agree(self):
		self.assertIsNone(install_host.registered_manifest())
		install_host.register(self.app)
		self.reg.values[install_host.REG_KEYS[1]] = "elsewhere.json"
		self.assertIsNone(install_host.registered_manifest())
		del self.reg.values[install_host.REG_KEYS[1]]
		self.assertIsNone(install_host.registered_manifest())

	def test_unregister_is_idempotent(self):
		install_host.register(self.app)
		install_host.unregister()
		install_host.unregister()
		self.assertEqual(self.reg.values, {})


if __name__ == "__main__":
	unittest.main()
