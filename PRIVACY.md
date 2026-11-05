# Privacy policy

NVDA AI Copilot (the NVDA add-on, its local coordinator and the browser extension for Chrome, Edge
and Firefox) has no server of its own and the developer receives no data.

## What is sent, and to whom

Nothing is read or sent until you press an NVDA AI Copilot shortcut. Then the structure of the
current tab (element roles, names, headings, landmarks, form field states) and, unless you turned it
off, a screenshot of the area are sent from your computer to the AI provider you selected:

- Anthropic (Claude API), under Anthropic's own terms and privacy policy, using your own API key; or
- a model server on your own computer, in which case nothing leaves the computer.

Never sent: field values; password, one-time code and card fields (painted black in screenshots);
cross-origin frames such as payment forms; text typed into editable regions. Card numbers in page
text are masked, and links are sent without query strings and fragments. You can turn screenshots
off and list sites where nothing is sent at all.

## What is stored on your computer

In `%LOCALAPPDATA%\nvda-ai-copilot`:

- your Anthropic API key, encrypted for your Windows account;
- explanations you chose to keep for a site;
- this month's number of Claude requests, tokens and estimated cost (counts only, no questions or
  answers), for the usage command and the monthly limit;
- logs, which never contain AI answers or your questions.

Removing the add-on does not delete these; delete the key in the settings page first and remove the
folder by hand if you want them gone.

## Contact

Questions: open an issue at https://github.com/oplosy/nvda-ai-copilot/issues.
