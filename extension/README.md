# minsky browser extension

A Manifest V3 Chrome/Edge extension that injects a small "what are you trying to
accomplish?" panel into the SWAYAM course-catalog page. It calls a **local** minsky
API instance (see [../docs/api.md](../docs/api.md)) and renders the resolved filters,
a ranked course shortlist with real clickable links (when using live data), and the
plain-language rationale — directly on top of swayam.gov.in, without touching SWAYAM's
own filter UI at all.

This is a local development/demo tool, not published to any extension store.

## Prerequisites

Run the minsky API locally first:

```bash
cd minsky
pip install -e ".[api]"
uvicorn minsky.api:app --reload
```

By default it listens on `http://127.0.0.1:8000`.

## Install (unpacked)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select this `extension/` folder.
4. Click the extension's icon in the toolbar to open its settings popup:
   - **minsky API base URL** — defaults to `http://127.0.0.1:8000`; change it if you're
     running the API elsewhere.
   - **Intent parser** — `rule_based` (default, works with no setup) or `llm` (needs
     `ANTHROPIC_API_KEY` set wherever the API server runs).
   - **Course data** — `live` (default, queries SWAYAM's real course catalog) or
     `sample` (the synthetic demo catalog, useful if you want deterministic offline
     results).
   - Click **Test connection** to confirm the extension can reach the API.

## Use

Visit [swayam.gov.in](https://swayam.gov.in) (any page — the panel is injected
site-wide). A small circular "M" button appears in the bottom-right corner. Click it,
type a goal (e.g. *"I want to become job-ready in data analytics within 3 months"*),
and click **Resolve** (or Ctrl/Cmd+Enter).

## Why a background service worker does the fetch

`content.js` never calls the API directly — it sends a message to `background.js`,
which does the actual `fetch`. A content script's network requests run under the
*host page's* CSP (swayam.gov.in's own response headers), which could unpredictably
block or restrict them; the extension's background service worker has no such
restriction and only needs the `host_permissions` already declared in
`manifest.json`.

## Limitations

- No icons are bundled (Chrome shows its default puzzle-piece icon) — cosmetic only.
- This does not attempt to auto-fill SWAYAM's own (fragile, Polymer-based) filter
  dropdowns — it shows the resolved filters and a ranked shortlist with direct course
  links instead, which is both more robust and, per
  [../docs/case-study-swayam.md](../docs/case-study-swayam.md), the more useful
  outcome for the learner anyway.
- The minsky API's CORS is wide open (`allow_origins: ["*"]`) specifically to support
  this extension calling it from a content-script context — see the security caveat in
  [../docs/api.md](../docs/api.md). Only run the API locally, not exposed publicly,
  while using this extension.
