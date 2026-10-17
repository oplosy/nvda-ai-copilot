"""Build dist/nvdaAiCopilot-<version>.nvda-addon (a zip NVDA installs when you open it)."""

import re
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {
	"manifest.ini": HERE / "manifest.ini",
	"globalPlugins/nvdaAiCopilot/__init__.py": HERE / "globalPlugins" / "nvdaAiCopilot" / "__init__.py",
	# One key store implementation for the add-on and the coordinator.
	"globalPlugins/nvdaAiCopilot/secret.py": HERE.parent / "coordinator" / "secret.py",
}


def main():
	version = re.search(r"^version = (\S+)$", FILES["manifest.ini"].read_text(encoding="utf-8"), re.M).group(1)
	out = HERE / "dist" / f"nvdaAiCopilot-{version}.nvda-addon"
	out.parent.mkdir(exist_ok=True)
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
		for name, src in FILES.items():
			z.write(src, name)
	print(out)


if __name__ == "__main__":
	main()
