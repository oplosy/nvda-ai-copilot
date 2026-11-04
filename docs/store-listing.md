# Store listings (draft)

Texts and answers for the Chrome Web Store, Edge Add-ons and the NVDA Add-on Store. Upload
`dist/nvda-ai-copilot-extension-<version>.zip` and the `.nvda-addon` from the GitHub release.

## Chrome Web Store / Edge Add-ons

**Name:** NVDA AI Copilot

**Summary** (132 characters max):
Companion for the NVDA AI Copilot add-on: lets the NVDA screen reader ask AI about unlabeled buttons, forms and tables on a page.

**Category:** Accessibility

**Description:**

NVDA AI Copilot helps NVDA screen reader users with the parts of a web page a screen reader cannot
make sense of: unlabeled buttons, missing headings, silent page updates, confusing forms, tables
and charts.

This extension is one part of NVDA AI Copilot and does nothing on its own. Install the NVDA add-on
from https://github.com/oplosy/nvda-ai-copilot/releases/latest first; it includes the local
coordinator this extension talks to.

When you press an NVDA AI Copilot shortcut in NVDA, the extension reads the structure of the current
tab (element roles, names, headings, landmarks, form field states) and, if you allow screenshots, a
screenshot with password, one-time code and card fields painted black. It hands this to the
coordinator on your computer, which sends it to the AI model you chose (Claude, or a model on your
own computer). The answer is spoken by NVDA, always starting with "AI comment:".

- Nothing is read or sent unless you press a shortcut.
- Field values are never read. Password, one-time code and card fields never reach the model.
- You can turn screenshots off and list sites where nothing is sent.
- The only action the extension takes on a page is moving focus to an element you asked for. It
  never clicks, types or submits.

**Single purpose:** Give the NVDA AI Copilot screen reader add-on, on the user's request, a
description of the current page so it can explain inaccessible elements and move focus to them.

**Permission justifications:**

- `nativeMessaging`: the extension only talks to the NVDA AI Copilot coordinator installed on the
  same computer by the NVDA add-on; that is how the screen reader's request reaches the page.
- Host permission `<all_urls>`: a screen reader user needs help on whatever site they are on, so the
  content script must be available on every page. It reads the page only when the user presses a
  shortcut in NVDA.
- Remote code: none. All code is in the package.

**Data usage** (Chrome "Privacy practices" form):

- Website content: collected only on the user's request, sent to the AI model the user chose
  (Anthropic's Claude API, or a server on the user's computer), not stored by the developer, not
  sold, not used for anything but answering that request.
- Not collected: personally identifiable information, health, financial and payment information,
  authentication information, personal communications, location, web history, user activity
  (keystrokes are never recorded; the extension only notes that a click or key press happened, to
  report what changed afterwards).
- Certify: not sold to third parties; not used or transferred for purposes unrelated to the single
  purpose; not used to determine creditworthiness or for lending.

**Privacy policy URL:** publish the section below (for example as `PRIVACY.md` in the repository)
and link it.

**Assets still needed:** a 128×128 icon (also add it to `extension/manifest.json` under `icons`),
at least one 1280×800 screenshot and a 440×280 promo tile.

**After approval:** add the store's extension ID to `EXTENSION_IDS` in
`coordinator/install_host.py` and release a new add-on version, or the store build cannot reach the
coordinator. Edge gives a different ID than Chrome; add both.

## Privacy policy

NVDA AI Copilot (the NVDA add-on, its local coordinator and the browser extension) has no server
of its own and the developer receives no data.

When you press a shortcut, page structure and, unless you turned it off, a masked screenshot of the
current tab are sent from your computer to the AI provider you selected: Anthropic (Claude API),
under Anthropic's own terms and privacy policy, using your own API key; or a model server on your
own computer, in which case nothing leaves the computer. Field values, password, one-time code and
card fields, cross-origin frames and text typed into editable regions are never sent. Card numbers in
page text are masked, and links are sent without query strings and fragments.

On your computer the add-on stores your API key encrypted for your Windows account, explanations
you chose to keep for a site, and logs that do not contain AI answers or your questions, all in
`%LOCALAPPDATA%\nvda-ai-copilot`. Removing the add-on does not delete them; delete the key in the
settings page and the folder by hand.

## NVDA Add-on Store

Submit through the add-on registration issue form of the `nvaccess/addon-datastore` repository on
GitHub, with:

- Download URL: the `.nvda-addon` asset of the GitHub release (a stable release URL, not a
  workflow artifact).
- Publisher: oplosy. Source URL: https://github.com/oplosy/nvda-ai-copilot. Licence: add one to the
  repository first; the store asks for it.
- Channel: stable.

The store scans the package with VirusTotal. The package contains python.org's signed embedded
Python and the packages from `coordinator/requirements.txt`; mention that in the submission so a
reviewer is not surprised by `python.exe` inside an add-on.
