# Dev setup

In Chrome browse mode:

- **NVDA+Alt+Shift+E**: explain the navigator object. The element is grounded first, then the
  coordinator sends its value-free DOM description and a masked screenshot crop to Claude
  (`claude-opus-5-5`, effort `low`). The answer is spoken as `AI yorumu: …`.
- **NVDA+Alt+Shift+P**: summarize the page. The extension sends a value-free outline (headings,
  landmarks, alerts, controls with names, start of the main text) and a masked screenshot of the
  viewport. No grounding needed.
- **NVDA+Alt+Shift+F**: find. Asks what to look for; the model picks one element from the
  outline (the JSON schema only allows IDs the extension issued, and the coordinator checks again),
  the extension focuses it (non-focusable elements get a temporary `tabindex=-1`) and NVDA follows
  focus. Focus is the only action; nothing is clicked or submitted.
- **NVDA+Alt+Shift+L**: grounding only (debug). Speaks the extension element ID (`e_N`).

The extension talks to the active tab of the last focused Chrome window. Any page load wakes the
service worker and reconnects the coordinator if it was stopped.

Flow: NVDA add-on → 127.0.0.1 (token from session file) → coordinator → native messaging →
extension service worker → content script of the active tab. If the bounding box is ambiguous,
the coordinator marks the candidates with `nvai-<nonce>-e_N` classes, the add-on polls the IA2
`class` attribute and asks again with the nonce, and the markers are removed.

Privacy: the extension never reads field values; password/OTP/card fields are painted black in
the screenshot; the coordinator drops any `value` keys and masks Luhn-valid card numbers in text
before the request leaves the machine (`coordinator/privacy.py`). Page data is sent to the model
as untrusted data inside `<page_data>`.

## One-time setup

1. Coordinator environment (Python 3.10+):

   ```powershell
   cd coordinator; python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt
   ```

2. API key: set `ANTHROPIC_API_KEY` as a **user** environment variable (System → Environment
   Variables), then restart Chrome fully. Chrome starts the coordinator, so the coordinator only
   sees variables Chrome was started with.
3. Chrome → `chrome://extensions` → Developer mode → *Load unpacked* → select `extension/`.
   The ID is always `ijifaphfddholfknhblhfnoajaekjgnj` (pinned by `key` in the manifest).
4. Register the native host (the ID argument is only needed if you change the key):

   ```powershell
   python coordinator\install_host.py
   ```

   This writes `coordinator/com.nvda_ai_copilot.coordinator.json` and the key
   `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.nvda_ai_copilot.coordinator`.
5. Reload the extension (or restart Chrome). Reload any tab that was open before the extension.
6. NVDA add-on: build the package and open it; NVDA asks to install and restart.

   ```powershell
   python nvda-addon\build.py
   ```

   The package (`nvda-addon/dist/nvdaAiCopilot-<version>.nvda-addon`) also contains the spike
   commands from `docs/spike-dom-mapping.md`. Rebuild and reinstall after changing the plugin.

## Checks

- Coordinator running: `%LOCALAPPDATA%\nvda-ai-copilot\session.json` exists while Chrome is open.
- Coordinator log: `%LOCALAPPDATA%\nvda-ai-copilot\coordinator.log` (`locate` and `explain` lines).
- Extension errors: `chrome://extensions` → NVDA AI Copilot → *service worker* → Console.
- NVDA log: lines starting with `nvdaAiCopilot:`.

Bring back the NVDA log lines and the matching `coordinator.log` lines for each test case A–E in
`docs/spike-dom-mapping.md`, plus a few NVDA+Alt+Shift+E answers on real sites.

## Tests

```powershell
cd coordinator; .venv\Scripts\python -m unittest
```

```powershell
node --test extension/grounding.test.js extension/context.test.js
```
