"""Each store zip keeps only the manifest keys its browser reads, and the IDs match the host registration."""

import json
import sys
import unittest
from pathlib import Path

import build_extension

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coordinator"))
import install_host  # noqa: E402

MANIFEST = json.loads((build_extension.EXT / "manifest.json").read_text(encoding="utf-8"))


class ManifestTest(unittest.TestCase):
	def test_chrome_zip_runs_a_service_worker_without_firefox_keys(self):
		m = build_extension.chrome_manifest(MANIFEST)
		self.assertEqual(m["background"], {"service_worker": "background.js"})
		self.assertNotIn("browser_specific_settings", m)
		self.assertNotIn("key", m)
		self.assertEqual(build_extension.loaded_files(m)[0], "background.js")

	def test_firefox_zip_loads_context_before_the_background_script(self):
		m = build_extension.firefox_manifest(MANIFEST)
		self.assertEqual(m["background"], {"scripts": ["context.js", "background.js"]})
		self.assertNotIn("key", m)
		self.assertEqual(build_extension.loaded_files(m)[:2], ["context.js", "background.js"])

	def test_gecko_id_is_the_one_the_native_host_allows(self):
		self.assertEqual(MANIFEST["browser_specific_settings"]["gecko"]["id"], install_host.FIREFOX_ID)

	def test_source_manifest_is_not_changed(self):
		before = json.dumps(MANIFEST, sort_keys=True)
		build_extension.chrome_manifest(MANIFEST)
		build_extension.firefox_manifest(MANIFEST)
		self.assertEqual(json.dumps(MANIFEST, sort_keys=True), before)


if __name__ == "__main__":
	unittest.main()
