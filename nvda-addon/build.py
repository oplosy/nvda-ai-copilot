"""Build dist/nvdaAiCopilot-<version>.nvda-addon (a zip NVDA installs when you open it)."""

import re
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {
	"manifest.ini": HERE / "manifest.ini",
	"globalPlugins/nvdaAiCopilot.py": HERE / "globalPlugins" / "nvdaAiCopilot.py",
	"globalPlugins/nvaiSpike.py": HERE / "spike" / "nvaiSpike.py",
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
