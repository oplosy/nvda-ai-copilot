import tempfile
import unittest
from pathlib import Path
from unittest import mock

import llm
import secret


class SecretTest(unittest.TestCase):
	def setUp(self):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		patcher = mock.patch.object(secret, "KEY_FILE", Path(tmp.name) / "sub" / "api-key.bin")
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_roundtrip_is_encrypted_at_rest(self):
		secret.save_key("sk-ant-test-123")
		self.assertNotIn(b"sk-ant", secret.KEY_FILE.read_bytes())
		self.assertEqual(secret.load_key(), "sk-ant-test-123")

	def test_missing_key_is_none_and_delete_is_idempotent(self):
		self.assertIsNone(secret.load_key())
		secret.save_key("k")
		secret.delete_key()
		secret.delete_key()
		self.assertFalse(secret.has_key())

	def test_paste_mistakes_are_rejected(self):
		for bad in ("", "sk ant", "sk-ant\n", "anahtarı"):
			with self.assertRaises(ValueError):
				secret.save_key(bad)
		self.assertFalse(secret.has_key())

	def test_corrupt_file_is_an_os_error(self):
		secret.KEY_FILE.parent.mkdir(parents=True)
		secret.KEY_FILE.write_bytes(b"not a dpapi blob")
		with self.assertRaises(OSError):
			secret.load_key()

	def test_client_follows_the_saved_key(self):
		self.addCleanup(setattr, llm, "_client", None)
		secret.save_key("sk-ant-one")
		first = llm.default_client()
		self.assertIs(llm.default_client(), first)
		secret.save_key("sk-ant-two")
		self.assertEqual(llm.default_client().api_key, "sk-ant-two")

	def test_undecryptable_key_is_an_llm_error(self):
		secret.KEY_FILE.parent.mkdir(parents=True)
		secret.KEY_FILE.write_bytes(b"x")
		with self.assertRaises(llm.LLMError):
			llm.default_client()


if __name__ == "__main__":
	unittest.main()
