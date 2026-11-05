# Install (end users)

You need Windows 10 or 11 (64-bit), NVDA 2024.1 or newer, Google Chrome or Microsoft Edge, and an
Anthropic API key (or a local model, see below).

1. **NVDA add-on:** download `nvdaAiCopilot-<version>.nvda-addon` from the
   [latest release](https://github.com/oplosy/nvda-ai-copilot/releases/latest) and open it. NVDA asks
   to install and restart. The add-on carries the coordinator (the local service that talks to the
   AI): on its first start it copies it to `%LOCALAPPDATA%\Programs\nvda-ai-copilot\<version>` and
   registers it with Chrome and Edge. Nothing else to run, and the browsers can stay open.
2. **Browser extension:** install *NVDA AI Copilot* from the Chrome Web Store (Edge: Edge Add-ons).
   Until the store listing is live: download *Source code (zip)* from the same release, extract it,
   open `chrome://extensions` (Edge: `edge://extensions`), turn on Developer mode, choose *Load
   unpacked* and select the `extension` folder. Reload any tab that was open before.
3. **API key:** NVDA menu → Preferences → Settings → *NVDA AI Copilot*. Paste the key and press OK.
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

**Updates:** install the new `.nvda-addon` the same way. The new version gets its own folder and the
browsers switch to it; the old folder is removed on a later NVDA start, once the browser has let go
of it.

**Uninstall:** remove the add-on in NVDA's Add-on Store (this unregisters the coordinator and deletes
its folder) and the extension in Chrome. The saved API key and logs stay in
`%LOCALAPPDATA%\nvda-ai-copilot`; delete the key in the settings page first if you want it gone.

**Coming from 0.2.0 (zip and install.bat):** just install the new add-on. It registers its own copy,
and the old files in `%LOCALAPPDATA%\Programs\nvda-ai-copilot` are removed on a later NVDA start.
