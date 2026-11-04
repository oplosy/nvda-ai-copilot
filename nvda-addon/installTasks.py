# NVDA runs onUninstall when the add-on is removed: unregister the coordinator from Chrome and Edge
# and delete its installed copies. The saved API key and the logs in %LOCALAPPDATA%\nvda-ai-copilot
# stay; the settings panel can delete the key before removing the add-on.

import importlib.util
import os
import shutil


def _load(name):
	path = os.path.join(os.path.dirname(__file__), "globalPlugins", "nvdaAiCopilot", f"{name}.py")
	spec = importlib.util.spec_from_file_location(f"nvdaAiCopilot_{name}", path)
	assert spec and spec.loader
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def onUninstall():
	from logHandler import log

	try:
		_load("install_host").unregister()
	except OSError as e:
		log.error(f"nvdaAiCopilot: could not unregister the coordinator: {e}")
	# A running coordinator keeps its folder locked; whatever stays is removed by the next install.
	shutil.rmtree(_load("bundle").INSTALL_ROOT, ignore_errors=True)
