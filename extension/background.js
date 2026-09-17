// Service worker: does the actual cross-origin fetch to the local minsky API.
//
// This runs in the extension's own background context rather than the content
// script, deliberately -- a fetch issued directly from a content script runs
// under the *page's* CSP (swayam.gov.in's own headers), which could block or
// restrict it unpredictably. The background service worker has no such
// restriction and only needs the host_permissions declared in manifest.json.

const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://127.0.0.1:8000",
  parser: "rule_based",
  courseSource: "live",
};

async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...stored };
}

async function resolveIntent(intentText, topN) {
  const settings = await getSettings();
  const url = `${settings.apiBaseUrl.replace(/\/$/, "")}/resolve`;

  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent: intentText,
        top_n: topN || 5,
        parser: settings.parser,
        course_source: settings.courseSource,
      }),
    });
  } catch (err) {
    throw new Error(
      `Could not reach the minsky API at ${settings.apiBaseUrl}. ` +
        `Is it running? (uvicorn minsky.api:app). Details: ${err.message}`
    );
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.error ? body.error : `HTTP ${response.status}`;
    throw new Error(`minsky API error: ${detail}`);
  }
  return body;
}

async function checkHealth() {
  const settings = await getSettings();
  const url = `${settings.apiBaseUrl.replace(/\/$/, "")}/health`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "MINSKY_RESOLVE") {
    resolveIntent(message.intent, message.topN)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // keep the message channel open for the async response
  }
  if (message && message.type === "MINSKY_HEALTH_CHECK") {
    checkHealth()
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
  return false;
});
