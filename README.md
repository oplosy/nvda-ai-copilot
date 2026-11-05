# NVDA AI Copilot

AI help for the parts of a web page that a screen reader cannot make sense of: unlabeled buttons,
missing headings, silent page updates, confusing forms and tables. You press a shortcut in Chrome,
Edge or Firefox and NVDA speaks an answer from Claude, sentence by sentence as it is written.

It does not fix the site and it does not change how NVDA works. AI output only comes when you ask
for it, and it always starts with **"AI comment:"** (Turkish: **"AI yorumu:"**) so you can tell it
apart from what the page itself says. Answers are in NVDA's language.

> Status: 0.5.1, early.

## What it can do

In Chrome, Edge or Firefox browse mode:

| Shortcut | Command | What you get |
| --- | --- | --- |
| NVDA+Alt+Shift+E | Explain | What the element under the navigator is and what it does |
| NVDA+Alt+Shift+P | Summarize | What the page is for, its main areas, actions, dialogs and errors |
| NVDA+Alt+Shift+F | Find | Type what you look for; focus moves to the best match |
| NVDA+Alt+Shift+R | Form help | What still needs filling in and how to fix each error |
| NVDA+Alt+Shift+T | Table help | What the table shows and what the current cell means |
| NVDA+Alt+Shift+C | What changed | What changed on the page since your last click or key press |
| NVDA+Alt+Shift+B | Sections | The page's parts named by AI; pick one and focus moves there |
| NVDA+Alt+Shift+Q | Follow-up | Ask a question about the last answer |
| NVDA+Alt+Shift+D | Chart help | What an SVG chart shows, values read from its geometry |
| NVDA+Alt+Shift+G / N | Guided task | Say your goal; AI gives one step at a time and moves focus, you act |
| NVDA+Alt+Shift+S | Report to the site | An AI-written accessibility issue report (WCAG, suggested fix) on the clipboard |
| NVDA+Alt+Shift+K | Keep | Save the last explanation for this site; next time it is spoken at once |
| NVDA+Alt+Shift+U | Usage | This month's Claude requests and their estimated cost in US dollars |

Every answer ends with what it is based on (a nearby label, a link, an icon), so you can judge it.

You can change the shortcuts in NVDA's Input gestures dialog.

The AI may only point to elements the extension found on the page, and moving focus is the only
thing it can do. It never clicks, types or submits, also in a guided task: there you do every step
and it warns before steps that pay, order, submit, send or delete.

## Privacy

Full policy: [PRIVACY.md](PRIVACY.md).

- Field values are never read. Password, one-time code and card fields, cross-origin frames such
  as payment forms, and text typed into editable regions never reach the model, as text or as
  pixels.
- In NVDA settings you can turn screenshots off (then none is taken) and list sites where Copilot
  sends nothing at all.
- Choose the Claude model by cost: Haiku 5.5 (fastest, about 40 times cheaper), Sonnet 5.5 or
  Opus 5.5 (most capable). NVDA+Alt+Shift+U says what this month cost so far (an estimate from
  list prices), and you can set a monthly limit in US dollars: once it is reached, Copilot stops
  calling Claude until the next month or until you raise it.
- Or use a local model instead of Claude: any OpenAI-compatible server on this computer (Ollama,
  LM Studio, llama.cpp) with a model that reads images. Only localhost addresses are accepted, and
  a broken local setup is an error, never a silent switch to the cloud.
- Card numbers that appear in page text are masked before anything leaves your computer.
- Links are sent without their query string and fragment, which can carry tokens.
- Page content is passed to the model as untrusted data, so text on the page cannot give it orders.
- The API key is encrypted for your Windows account (DPAPI). Logs never contain AI answers or your
  questions.

## How it works

```
NVDA add-on  ──localhost──▶  coordinator (Python)  ──native messaging──▶  browser extension
 shortcuts, speech            privacy filter, Claude,                      reads the DOM, masked
 settings                     what actions are allowed                     screenshot, moves focus
```

- `nvda-addon/`: NVDA global plugin: shortcuts, speech, settings panel.
- `coordinator/`: local Python service: combines context, filters private data, calls Claude,
  decides which actions are allowed.
- `extension/`: Chrome/Edge/Firefox MV3 extension: DOM (same-origin frames included), ARIA, bounding
  boxes, masked screenshots, focus.
- `eval/`: answer quality and speed check on deliberately inaccessible pages.

## Install

Needs Windows 10 or 11 (64-bit), NVDA 2024.1 or newer, Google Chrome, Microsoft Edge or
Mozilla Firefox 128 or newer and an
[Anthropic API key](https://console.anthropic.com/) (or a local model). Install the `.nvda-addon`
from the [latest release](https://github.com/oplosy/nvda-ai-copilot/releases/latest), which carries
the coordinator, and the browser extension. See [docs/install.md](docs/install.md).

## Development

Setup, release build and test commands: [docs/dev-setup.md](docs/dev-setup.md).

```powershell
cd coordinator; .venv\Scripts\python -m unittest
npm install; node --test "extension/*.test.js"
coordinator\.venv\Scripts\python eval\run.py --dry-run   # without --dry-run it calls the API
```

How NVDA's navigator object is matched to a DOM element: [docs/spike-dom-mapping.md](docs/spike-dom-mapping.md).

## Not in scope

Submitting forms, payments, autonomous multi-step tasks and CAPTCHA solving.

## License

GPL-2.0, like NVDA itself. See [LICENSE](LICENSE).
