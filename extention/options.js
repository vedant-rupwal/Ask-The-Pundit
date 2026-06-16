const DEFAULT_SERVER_URL = "https://vedantrupwal-ask-the-pandit.hf.space";
const STORAGE_KEY = "askThePanditServerUrl";

const form = document.getElementById("optionsForm");
const serverUrlInput = document.getElementById("serverUrl");
const status = document.getElementById("status");
const hybridQueryLog = document.getElementById("hybridQueryLog");
const chromaResultsLog = document.getElementById("chromaResultsLog");
const systemPromptLog = document.getElementById("systemPromptLog");

function setStatus(message) {
  status.textContent = message;
  if (!message) {
    return;
  }

  window.setTimeout(() => {
    if (status.textContent === message) {
      status.textContent = "";
    }
  }, 2000);
}

function setDeveloperLog({ hybridQuery, chromaResults, systemPrompt }) {
  hybridQueryLog.textContent = hybridQuery || "No query has been logged yet.";
  chromaResultsLog.textContent = chromaResults || "No scripture has been logged yet.";
  systemPromptLog.textContent = systemPrompt || "No prompt has been logged yet.";
}

async function fetchLastQueryLog(serverUrl) {
  try {
    const response = await fetch(`${serverUrl}/last-query-log`);
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    setDeveloperLog({
      hybridQuery: data.hybrid_query,
      chromaResults: data.raw_chroma_results,
      systemPrompt: data.system_prompt,
    });
  } catch (error) {
    setDeveloperLog({
      hybridQuery: `Unable to load developer info from ${serverUrl}.`,
      chromaResults: "Check that the FastAPI server is running and reachable.",
      systemPrompt: String(error),
    });
  }
}

function loadOptions() {
  chrome.storage.local.get([STORAGE_KEY], (items) => {
    const savedUrl = items[STORAGE_KEY];
    const serverUrl = savedUrl || DEFAULT_SERVER_URL;
    serverUrlInput.value = serverUrl;
    void fetchLastQueryLog(serverUrl);
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();

  const serverUrl = serverUrlInput.value.trim() || DEFAULT_SERVER_URL;
  chrome.storage.local.set({ [STORAGE_KEY]: serverUrl }, () => {
    setStatus("Saved.");
    void fetchLastQueryLog(serverUrl);
  });
});

loadOptions();
