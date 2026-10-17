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
- **NVDA+Alt+Shift+R**: form help. Grounds the navigator object, then describes the surrounding
  form (`form`, `[role=form]` or `fieldset`, else the page): labels, required, filled (yes/no only),
  invalid with validity flags, error texts, buttons. Explains what to fill and how to fix errors.
  `validationMessage` is never sent because Chrome's text can quote what was typed.
- **NVDA+Alt+Shift+T**: table help. Grounds the navigator object and describes the table around
  it (caption, first 30 rows x 12 columns of cell text, marked headers, sizes, the current cell).
- **NVDA+Alt+Shift+C**: what changed. The extension records DOM changes since the last click or
  key press in the page (added, text, attribute and removed content; never inside fields or
  `contenteditable`) and the model says what they mean. No changes: answered without the model.
- **NVDA+Alt+Shift+B**: AI section list. The extension splits the page into up to 40 visible blocks;
  the model names 3-12 parts using only those IDs (JSON schema). A list dialog shows them and focus
  moves to the chosen part; the coordinator only accepts focus for IDs from the last list.
- **NVDA+Alt+Shift+Q**: follow-up question about the last AI answer (5 minutes), on the same page
  data and screenshot. Follow-ups chain.
- **NVDA+Alt+Shift+L**: grounding only (debug). Speaks the extension element ID (`e_N`).

Settings travel with every request from the add-on (NVDA settings → NVDA AI Copilot): send
screenshots (off: the extension takes none), sites where Copilot is off (the coordinator refuses
before anything reaches the model, follow-ups included) and NVDA's language, which the prompts
answer in. Text answers stream: the coordinator sends finished sentences as `partial` lines and
the add-on speaks them at once. Element explanations are cached for 30 minutes per element state.
The coordinator log has extension, first-sentence and total times for every request.

Same-origin iframes are read like the page; cross-origin frames are masked whole in screenshots.
What-changed watches the top document only.

All text sent to the model goes through `safeText()` in `extension/context.js`, which skips form
fields and `contenteditable` regions, so typed text never leaves through `innerText`.

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

2. API key: enter it in NVDA → Preferences → Settings → NVDA AI Copilot (after step 6). It is
   stored DPAPI-encrypted in `%LOCALAPPDATA%\nvda-ai-copilot\api-key.bin` (`coordinator/secret.py`)
   and picked up without restarting Chrome. Without a saved key the coordinator falls back to the
   `ANTHROPIC_API_KEY` user environment variable, which only reaches it after a full Chrome restart.
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

   The package (`nvda-addon/dist/nvdaAiCopilot-<version>.nvda-addon`) does not contain the spike
   commands; load `nvda-addon/spike/nvaiSpike.py` as `docs/spike-dom-mapping.md` describes.
   Rebuild and reinstall after changing the plugin.

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
npm install
node --test "extension/*.test.js"
```

Answer quality and speed (`eval/`): 11 inaccessible cases built by the real extension code in
jsdom (no screenshots), sent through the real coordinator. Without `--dry-run` it calls the API once
per case; `--model` compares another model.

```powershell
coordinator\.venv\Scripts\python eval\run.py --dry-run
coordinator\.venv\Scripts\python eval\run.py
```

Add-on translations: English source strings in `_()`, `nvda-addon/locale/<lang>/LC_MESSAGES/nvda.po`.
`build.py` compiles them and stops if a string has no translation.

## Release build

```powershell
cd coordinator; .venv\Scripts\python build_dist.py
python nvda-addon\build.py
```

`build_dist.py` writes `coordinator/dist/nvda-ai-copilot-coordinator.zip`: python.org's embedded
Python 3.12.10 (SHA-256 pinned), the packages installed in the dev venv (`pip freeze`), the
coordinator and `install.bat` / `uninstall.bat` from `coordinator/package/`. `run_host.bat` uses the
dev `.venv` when it exists and the embedded Python otherwise. End-user steps: `docs/install.md`.
