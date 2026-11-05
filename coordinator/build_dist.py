"""Build build/nvda-ai-copilot/ for end users: embedded Python, the dependencies installed in the
dev venv (the tested set) and the coordinator. Run it from the dev venv:

    .venv\\Scripts\\python build_dist.py

nvda-addon/build.py packs this folder into the add-on, which installs and registers it
(docs/install.md).
"""

import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
OUT = BUILD / "nvda-ai-copilot"
# Same version as the dev venv, so its binary wheels (pydantic-core, jiter) fit.
PY_VERSION = "3.12.10"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
# Hash of the file whose MD5 matched python.org's release page (fe8ef205f2e9c3ba44d0cf9954e1abd3).
PY_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
APP_FILES = ["host.py", "llm.py", "labels.py", "usage.py", "privacy.py", "grounding.py", "native.py", "secret.py", "install_host.py", "run_host.bat"]


def embedded_python():
	cached = BUILD / PY_URL.rsplit("/", 1)[1]
	if not cached.exists():
		BUILD.mkdir(exist_ok=True)
		with urllib.request.urlopen(PY_URL, timeout=60) as r:
			cached.write_bytes(r.read())
	if hashlib.sha256(cached.read_bytes()).hexdigest() != PY_SHA256:
		cached.unlink()
		sys.exit(f"checksum mismatch for {PY_URL}; download removed")
	return cached


def main():
	if sys.version.split()[0] != PY_VERSION or sys.prefix == sys.base_prefix:
		sys.exit(f"run this with the dev venv's Python {PY_VERSION}")
	shutil.rmtree(OUT, ignore_errors=True)
	with zipfile.ZipFile(embedded_python()) as z:
		z.extractall(OUT / "python")
	# The ._pth file is the whole import path of embedded Python; add the app and its packages.
	pth = next((OUT / "python").glob("python*._pth"))
	pth.write_text(pth.read_text() + "..\\app\n..\\site-packages\n")
	lock = subprocess.run([sys.executable, "-m", "pip", "freeze"], check=True, capture_output=True, text=True).stdout
	(BUILD / "requirements.lock").write_text(lock)
	subprocess.run(
		[sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--target", OUT / "site-packages", "-r", BUILD / "requirements.lock"],
		check=True,
	)
	(OUT / "app").mkdir()
	for name in APP_FILES:
		shutil.copy2(HERE / name, OUT / "app" / name)
	print(OUT)


if __name__ == "__main__":
	main()
