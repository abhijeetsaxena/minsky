const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://127.0.0.1:8000",
  parser: "rule_based",
  courseSource: "live",
};

const apiBaseUrlInput = document.getElementById("apiBaseUrl");
const parserSelect = document.getElementById("parser");
const courseSourceSelect = document.getElementById("courseSource");
const saveButton = document.getElementById("save");
const testButton = document.getElementById("testConnection");
const status = document.getElementById("status");

async function load() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  apiBaseUrlInput.value = stored.apiBaseUrl;
  parserSelect.value = stored.parser;
  courseSourceSelect.value = stored.courseSource;
}

async function save() {
  await chrome.storage.local.set({
    apiBaseUrl: apiBaseUrlInput.value.trim() || DEFAULT_SETTINGS.apiBaseUrl,
    parser: parserSelect.value,
    courseSource: courseSourceSelect.value,
  });
  status.style.color = "#1a3e8c";
  status.textContent = "Saved.";
}

function testConnection() {
  status.style.color = "#1a3e8c";
  status.textContent = "Checking...";
  save().then(() => {
    chrome.runtime.sendMessage({ type: "MINSKY_HEALTH_CHECK" }, (response) => {
      if (chrome.runtime.lastError) {
        status.style.color = "#a4262c";
        status.textContent = chrome.runtime.lastError.message;
        return;
      }
      if (response && response.ok) {
        status.style.color = "#1a7a3e";
        status.textContent = "Connected ✓";
      } else {
        status.style.color = "#a4262c";
        status.textContent = (response && response.error) || "Could not connect.";
      }
    });
  });
}

saveButton.addEventListener("click", save);
testButton.addEventListener("click", testConnection);
load();
