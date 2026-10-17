# Install (end users)

You need Windows 10 or 11 (64-bit), NVDA 2024.1 or newer, Google Chrome and an Anthropic API key.

1. **Coordinator:** close Chrome. Extract `nvda-ai-copilot-coordinator.zip` to any folder and run
   `install.bat` there. It copies itself to `%LOCALAPPDATA%\Programs\nvda-ai-copilot` and registers
   with Chrome; the extracted folder can be deleted afterwards.
2. **Chrome extension:** until it is published in the Chrome Web Store, open `chrome://extensions`,
   turn on Developer mode, choose *Load unpacked* and select the `extension` folder.
3. **NVDA add-on:** open `nvdaAiCopilot-<version>.nvda-addon`; NVDA asks to install and restart.
4. **API key:** NVDA menu → Preferences → Settings → *NVDA AI Copilot*. Paste the key and press OK.
   It is encrypted for your Windows account and is never shown again; check *Kayıtlı anahtarı sil* to
   remove it.

Shortcuts in Chrome browse mode: NVDA+Alt+Shift+E (explain element), P (summarize page),
F (find), R (form help). AI output always starts with "AI yorumu:".

**Uninstall:** run `uninstall.bat` in `%LOCALAPPDATA%\Programs\nvda-ai-copilot`, remove the add-on
in NVDA's Add-on Store and the extension in Chrome. Logs stay in `%LOCALAPPDATA%\nvda-ai-copilot`.
