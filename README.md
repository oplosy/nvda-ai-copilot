# NVDA AI Copilot

AI help for the parts of a web page that a screen reader cannot make sense of: unlabeled buttons,
missing headings, silent page updates, confusing forms. You press a shortcut in Chrome and NVDA
speaks an answer from Claude.

It does not fix the site and it does not change how NVDA works. AI output only comes when you ask
for it, and it always starts with **"AI yorumu:"** so you can tell it apart from what the page
itself says.

> Status: 0.1.0, early. The answers are in Turkish for now.

## What it can do

In Chrome browse mode:

| Shortcut | Command | What you get |
| --- | --- | --- |
| NVDA+Alt+Shift+E | Explain | What the element under the navigator is and what it does |
| NVDA+Alt+Shift+P | Summarize | What the page is for, its main areas, actions, dialogs and errors |
| NVDA+Alt+Shift+F | Find | Type what you look for; focus moves to the best match |
| NVDA+Alt+Shift+R | Form help | What still needs filling in and how to fix each error |
| NVDA+Alt+Shift+C | What changed | What changed on the page since your last click or key press |
| NVDA+Alt+Shift+B | Sections | The page's parts named by AI; pick one and focus moves there |
| NVDA+Alt+Shift+Q | Follow-up | Ask a question about the last answer |

You can change the shortcuts in NVDA's Input gestures dialog.

The AI may only point to elements the extension found on the page, and moving focus is the only
thing it can do. It never clicks, types or submits.

## Privacy

- Field values are never read. Password, one-time code and card fields, iframes such as payment
  forms, and text typed into editable regions never reach the model, as text or as pixels.
- Card numbers that appear in page text are masked before anything leaves your computer.
- Links are sent without their query string and fragment, which can carry tokens.
- Page content is passed to the model as untrusted data, so text on the page cannot give it orders.
- The API key is encrypted for your Windows account (DPAPI). Logs never contain AI answers or your
  questions.

## How it works

```
NVDA add-on  ──localhost──▶  coordinator (Python)  ──native messaging──▶  Chrome extension
 shortcuts, speech            privacy filter, Claude,                      reads the DOM, masked
 settings                     what actions are allowed                     screenshot, moves focus
```

- `nvda-addon/`: NVDA global plugin: shortcuts, speech, settings panel.
- `coordinator/`: local Python service: combines context, filters private data, calls Claude,
  decides which actions are allowed.
- `extension/`: Chrome MV3 extension: DOM, ARIA, bounding boxes, masked screenshots, focus.

## Install

Needs Windows 10 or 11 (64-bit), NVDA 2024.1 or newer, Google Chrome and an
[Anthropic API key](https://console.anthropic.com/). See [docs/install.md](docs/install.md).

## Development

Setup, release build and test commands: [docs/dev-setup.md](docs/dev-setup.md).

```powershell
cd coordinator; .venv\Scripts\python -m unittest
npm install; node --test "extension/*.test.js"
```

How NVDA's navigator object is matched to a DOM element: [docs/spike-dom-mapping.md](docs/spike-dom-mapping.md).

## Not in scope

Submitting forms, payments, autonomous multi-step tasks and CAPTCHA solving.
