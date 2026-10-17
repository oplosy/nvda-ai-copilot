# Install (end users)

You need Windows 10 or 11 (64-bit), NVDA 2024.1 or newer, Google Chrome or Microsoft Edge and an
Anthropic API key.

1. **Coordinator:** close Chrome and Edge. Extract `nvda-ai-copilot-coordinator.zip` to any folder and run
   `install.bat` there. It copies itself to `%LOCALAPPDATA%\Programs\nvda-ai-copilot` and registers
   with Chrome and Edge; the extracted folder can be deleted afterwards.
2. **Browser extension:** until it is published in the Chrome Web Store, open `chrome://extensions`
   (Edge: `edge://extensions`),
   turn on Developer mode, choose *Load unpacked* and select the `extension` folder.
3. **NVDA add-on:** open `nvdaAiCopilot-<version>.nvda-addon`; NVDA asks to install and restart.
4. **API key:** NVDA menu → Preferences → Settings → *NVDA AI Copilot*. Paste the key and press OK.
   It is encrypted for your Windows account and is never shown again; check *Kayıtlı anahtarı sil* to
   remove it.

Shortcuts in Chrome browse mode: NVDA+Alt+Shift+E (explain element), P (summarize page),
F (find), R (form help), T (table help), C (what changed after my last click or key press),
B (list of page parts; pick one to move there), Q (follow-up question about the last answer),
D (chart help), G and N (guided task: start, next step), S (accessibility report for the site, on
the clipboard), K (keep the last explanation for this site). AI
output always starts with "AI comment:" ("AI yorumu:" in Turkish) and is in NVDA's language.
Shortcuts can be changed in NVDA's Input gestures dialog, category NVDA AI Copilot.

**Privacy settings** (same NVDA settings page): turn off *Send screenshots to the AI* and no
screenshot is taken; list sites (for example your bank) where Copilot sends nothing.

**Claude model** (same settings page): Haiku 5.5 is the fastest and about 40 times cheaper than
Opus 5.5; Opus 5.5 is the most capable. A summary costs roughly 0.06 cents with Haiku and 2.5 cents
with Opus, billed to your Anthropic account.

**Local model** (optional, nothing leaves the computer): install an OpenAI-compatible server such as
[Ollama](https://ollama.com/), pull a model that can read images, then in the same settings page
choose *Local model server on this computer* and enter its address (Ollama:
`http://127.0.0.1:11434/v1`) and the model name. Answers are usually slower and less accurate than
Claude's; no API key is needed.

**Uninstall:** run `uninstall.bat` in `%LOCALAPPDATA%\Programs\nvda-ai-copilot`, remove the add-on
in NVDA's Add-on Store and the extension in Chrome. Logs stay in `%LOCALAPPDATA%\nvda-ai-copilot`.
