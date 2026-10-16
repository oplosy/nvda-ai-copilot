# Dev setup: grounding walking skeleton

Pressing **NVDA+Alt+Shift+L** in Chrome browse mode maps the navigator object to an extension
element ID (`e_N`) and speaks the result. No LLM yet.

Flow: NVDA add-on → 127.0.0.1 (token from session file) → coordinator → native messaging →
extension service worker → content script of the active tab. If the bounding box is ambiguous,
the coordinator marks the candidates with `nvai-<nonce>-e_N` classes, the add-on polls the IA2
`class` attribute and asks again with the nonce, and the markers are removed.

## One-time setup

Requires Python 3.10+ on `PATH` (Chrome starts the coordinator through `coordinator/run_host.bat`).

1. Chrome → `chrome://extensions` → Developer mode → *Load unpacked* → select `extension/`.
   Copy the extension ID.
2. Register the native host:

   ```powershell
   python coordinator\install_host.py <extension-id>
   ```

   This writes `coordinator/com.nvda_ai_copilot.coordinator.json` and the key
   `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.nvda_ai_copilot.coordinator`.
3. Reload the extension (or restart Chrome). Reload any tab that was open before the extension.
4. NVDA: with scratchpad loading enabled (see `docs/spike-dom-mapping.md`), copy
   `nvda-addon/globalPlugins/nvdaAiCopilot.py` to `%APPDATA%\nvda\scratchpad\globalPlugins\`
   and reload plugins (NVDA+Ctrl+F3).

## Checks

- Coordinator running: `%LOCALAPPDATA%\nvda-ai-copilot\session.json` exists while Chrome is open.
- Coordinator log: `%LOCALAPPDATA%\nvda-ai-copilot\coordinator.log` (one `locate` line per request).
- Extension errors: `chrome://extensions` → NVDA AI Copilot → *service worker* → Console.
- NVDA log: lines starting with `nvdaAiCopilot:`.

Bring back the NVDA log lines and the matching `coordinator.log` lines for each test case A–E in
`docs/spike-dom-mapping.md`.

## Tests

```powershell
cd coordinator; python -m unittest
```

```powershell
node --test extension/grounding.test.js
```
