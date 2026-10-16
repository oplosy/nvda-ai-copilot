# Spike: mapping the NVDA navigator object to a Chrome DOM element

Goal: when the user presses the copilot shortcut in browse mode, the coordinator must know
*which DOM element* the NVDA navigator object is, so the extension can describe it and the LLM
can only pick among extension-issued element IDs.

Verified against source (2026-10-16):

- NVDA `NVDAObjects/IAccessible/__init__.py`: `IA2Attributes` (parsed `IAccessible2::attributes`),
  `IA2UniqueID`, `location` = `accLocation` (screen pixels), `IA2TextTextInfo._setSelectionOffsets`
  → `IAccessibleText.AddSelection` / caret offset.
- NVDA `virtualBuffers/gecko_ia2.py`: Chrome's browse-mode buffer (`ChromeVBuf` subclasses it) keys
  nodes by `(windowHandle, IA2UniqueID)`.
- Chromium `ui/accessibility/platform/ax_platform_node_base.cc` `ComputeAttributes`: exposes
  `tag`, `xml-roles`, `display`, **`class`**, **`id`**, `html-input-name`, `src` (images), plus ARIA.
- Chromium `ax_platform_node_win.h`: no `ISimpleDOMNode`; `QueryService` only serves IA2 /
  IAccessible / text / table / value (and feature-gated `IChromeAccessible`).

## Options

| # | Method | NVDA side | Extension side | Deterministic? | Main risk |
|---|--------|-----------|----------------|----------------|-----------|
| 1 | HTML `id` | `IA2Attributes["id"]` | `getElementById` | Yes, if present and unique | Most unlabeled controls have no id; duplicate ids exist in the wild |
| 2 | Temporary marker class | `IA2Attributes["class"]` | Add `nvai-<elementId>` to candidates, remove after read | Yes, for any element in the a11y tree | Mutates DOM (class only, no semantics); needs a11y tree update latency; frameworks may overwrite `className` on re-render |
| 3 | Bounding box | `location` minus viewport origin, ÷ `devicePixelRatio` | IoU against `getBoundingClientRect` | No: parent/child often share a rect | Nested same-size boxes, overlays, iframes, page zoom, wrong viewport origin |
| 4 | Selection bridge | `makeTextInfo(ALL).updateSelection()` | `getSelection()` → common ancestor | Mostly, for rendered text-bearing nodes | Side effect: changes page selection (may fire `selectionchange`, may move NVDA caret) |
| 5 | Fingerprint | tag, role, name, ancestor chain | Same from DOM / `chrome.debugger` `Accessibility.*` | No | Only a verifier / tiebreaker |

Rejected:

- **`IA2UniqueID`**: browser-process platform ID. Not visible to content scripts; CDP `AXNodeId` is
  Blink's ID, a different number space. `chrome.automation` is not available on Windows.
- **`ISimpleDOMNode`**: Chromium does not implement it (see above).
- **Focus sync (`setFocus` → `document.activeElement`)**: only works for focusable elements, which are
  exactly the ones that are usually *not* broken. Option 4 covers more.
- **Coordinates for the LLM**: excluded by project rules; rects are used only for grounding.

### Hypothesis to confirm with the test

Primary: **1 when the id is unique, otherwise 2**. Verify the match with **3** (IoU) and the tag from **5**.
Option 4 is a fallback if Chromium's `class` attribute turns out to be stale or missing.

For option 2 the real flow would be: hotkey → coordinator asks extension to snapshot and tag
candidates with `nvai-e_123` → NVDA re-reads the navigator's `class` (retry until present, ~100–500 ms)
→ coordinator gets `e_123` → extension removes the markers. The marker *is* the extension's element ID.

## Running the spike

1. NVDA → Preferences → Settings → Advanced → enable *Enable loading custom code from Developer Scratchpad directory*.
2. Copy `nvda-addon/spike/nvaiSpike.py` to `%APPDATA%\nvda\scratchpad\globalPlugins\`.
3. NVDA menu → Tools → Reload plugins (or NVDA+Ctrl+F3).
4. Open the test page in Chrome, browse mode.

Shortcuts:

- **NVDA+Alt+Shift+I**: logs the navigator object's IA2 data, location, viewport origins and
  ancestor chain, and **copies a JS snippet to the clipboard**.
- **NVDA+Alt+Shift+S**: sets the browser selection to the navigator object (option 4).

Every log line starts with `NVAI-SPIKE`.

### Test cases

Use a page with these elements (any real site, or a local HTML file):

| Case | Element | What it tests |
|------|---------|---------------|
| A | `<button id="go">Go</button>` | Option 1 baseline |
| B | `<div role="button" onclick="..."><svg>…</svg></div>` without id | Options 2, 3, 4 on the typical broken control |
| C | `<a><span>Text</span></a>` where the link and span share a rect | Option 3 ambiguity |
| D | Same element scrolled off-screen | Option 3 with off-screen rects |
| E | Same page at Chrome zoom 150 % (Ctrl +) | DPR / zoom handling |
| F | Element inside an `<iframe>` | Known limit: snippet only checks the top document |

For each case:

1. Move the virtual cursor to the element, press **NVDA+Alt+Shift+I**.
2. Press F12, Console tab, paste (Ctrl+V), Enter. Copy the printed JSON.
3. Option 2 (case B): in the console run
   `document.querySelector('<selector>').classList.add('nvai-test-1')`, return to the page,
   press **NVDA+Alt+Shift+I** again and check whether `IA2Attributes.class` contains `nvai-test-1`.
   Repeat immediately and after ~1 s to see the latency.
4. Option 4 (case B): press **NVDA+Alt+Shift+S**, then **NVDA+Alt+Shift+I**, paste the snippet;
   look at `bySelection`. Also note if NVDA said anything or the virtual caret moved.

Bring back: the `NVAI-SPIKE inspect` log block and the console JSON for each case.

### Reading the result

- `rect_docRoot` vs `rect_renderWidget`: whichever has `iou` ≈ 1.0 on the right element tells us the
  correct viewport origin. `ambiguous_iou_gt_0_9` > 1 means option 3 alone cannot decide.
- `byId.count` must be 1 for option 1 to be trusted.
- `byMarker` present and correct → option 2 works.
- `bySelection.el` equal to the target (or its direct child) → option 4 works.
