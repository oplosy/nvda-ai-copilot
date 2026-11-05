"""Build dist/nvdaAiCopilot-<version>.nvda-addon (a zip NVDA installs when you open it).

Also compiles locale/<lang>/LC_MESSAGES/nvda.po to .mo and stops if a translation misses one of
the add-on's _("...") strings, so a release never speaks untranslated or stale text.
"""

import ast
import gettext
import io
import re
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE / "globalPlugins" / "nvdaAiCopilot" / "__init__.py"
FILES = {
	"manifest.ini": HERE / "manifest.ini",
	"installTasks.py": HERE / "installTasks.py",
	"globalPlugins/nvdaAiCopilot/__init__.py": PLUGIN,
	"globalPlugins/nvdaAiCopilot/bundle.py": PLUGIN.parent / "bundle.py",
	# One key store and one host registration for the add-on and the coordinator.
	"globalPlugins/nvdaAiCopilot/secret.py": HERE.parent / "coordinator" / "secret.py",
	"globalPlugins/nvdaAiCopilot/install_host.py": HERE.parent / "coordinator" / "install_host.py",
	# The add-on reads the coordinator's usage file to speak this month's usage.
	"globalPlugins/nvdaAiCopilot/usage.py": HERE.parent / "coordinator" / "usage.py",
	"doc/en/readme.html": HERE / "doc" / "en" / "readme.html",
}
# Written by coordinator/build_dist.py; the add-on installs it from its "coordinator" folder.
COORDINATOR = HERE.parent / "coordinator" / "build" / "nvda-ai-copilot"
# 70 (pending-install folder) + 150 + runtime __pycache__ suffixes stays under 260 for user names up to ~25 characters.
MAX_ARCHIVE_PATH = 150
MSGID = re.compile(r'\b_\(("(?:[^"\\]|\\.)*")\)')


def source_strings():
	return set(ast.literal_eval(m) for m in MSGID.findall(PLUGIN.read_text(encoding="utf-8")))


def read_po(path):
	"""msgid -> msgstr for single-context, non-plural entries with quoted (possibly continued) lines."""
	entries, current, key = {}, None, None
	for line in path.read_text(encoding="utf-8").splitlines() + [""]:
		line = line.strip()
		if line.startswith("msgid "):
			current, key = {"msgid": ast.literal_eval(line[6:]), "msgstr": ""}, "msgid"
		elif line.startswith("msgstr "):
			current["msgstr"], key = ast.literal_eval(line[7:]), "msgstr"
		elif line.startswith('"') and current:
			current[key] += ast.literal_eval(line)
		elif not line and current:
			entries[current["msgid"]] = current["msgstr"]
			current = None
	return entries


def mo_bytes(entries):
	"""GNU .mo file (no hash table) for the given msgid -> msgstr mapping."""
	keys = sorted(entries)
	ids = [k.encode("utf-8") for k in keys]
	strs = [entries[k].encode("utf-8") for k in keys]
	start = 7 * 4 + 16 * len(keys)
	offsets, data = [], b""
	for blob in ids + strs:
		offsets.append((len(blob), start + len(data)))
		data += blob + b"\0"
	header = struct.pack("<7I", 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + 8 * len(keys), 0, 0)
	table = b"".join(struct.pack("<2I", *o) for o in offsets)
	return header + table + data


def compile_locales():
	wanted = source_strings()
	out = {}
	for po in sorted(HERE.glob("locale/*/LC_MESSAGES/nvda.po")):
		entries = read_po(po)
		missing = sorted(s for s in wanted if not entries.get(s))
		if missing:
			sys.exit(f"{po}: untranslated strings:\n" + "\n".join(missing))
		mo = mo_bytes({k: v for k, v in entries.items() if k in wanted or k == ""})
		# Self-check: the standard gettext reader must see every translation.
		catalog = gettext.GNUTranslations(io.BytesIO(mo))
		assert all(catalog.gettext(s) == entries[s] for s in wanted), po
		out[po.relative_to(HERE).with_suffix(".mo").as_posix()] = mo
	for manifest in sorted(HERE.glob("locale/*/manifest.ini")):
		out[manifest.relative_to(HERE).as_posix()] = manifest.read_bytes()
	return out


def coordinator_files():
	"""Archive name -> source for the coordinator build; stops if it is missing or incomplete."""
	required = [COORDINATOR / "app" / "run_host.bat", COORDINATOR / "app" / "host.py", *COORDINATOR.glob("python/python*._pth")]
	if len(required) < 3 or not all(p.is_file() for p in required):
		sys.exit(f"{COORDINATOR} is missing or incomplete: run coordinator\\.venv\\Scripts\\python coordinator\\build_dist.py first, or pass --dev")
	files = {
		"coordinator/" + f.relative_to(COORDINATOR).as_posix(): f
		for f in sorted(COORDINATOR.rglob("*"))
		if f.is_file() and "__pycache__" not in f.parts and f.name != "com.nvda_ai_copilot.coordinator.json"
	}
	# NVDA unpacks the add-on to %APPDATA%\nvda\addons\nvdaAiCopilot.pendingInstall\ (about 70 characters
	# with a short user name) without long-path support. Keep the deepest file well inside MAX_PATH (260).
	longest = max(files, key=len)
	if len(longest) > MAX_ARCHIVE_PATH:
		sys.exit(f"{longest} is {len(longest)} characters (limit {MAX_ARCHIVE_PATH}); a dependency update made paths too long for NVDA to unpack")
	return files


def main():
	args = sys.argv[1:]
	if args not in ([], ["--dev"]):
		sys.exit("usage: python build.py [--dev]   (--dev: without the coordinator; register your checkout's yourself)")
	dev = args == ["--dev"]
	version = re.search(r"^version = (\S+)$", FILES["manifest.ini"].read_text(encoding="utf-8"), re.M).group(1)
	locales = compile_locales()
	files = dict(FILES) if dev else {**FILES, **coordinator_files()}
	out = HERE / "dist" / f"nvdaAiCopilot-{version}{'-dev' if dev else ''}.nvda-addon"
	out.parent.mkdir(exist_ok=True)
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
		for name, src in files.items():
			z.write(src, name)
		for name, data in locales.items():
			z.writestr(name, data)
	print(out)


if __name__ == "__main__":
	main()
