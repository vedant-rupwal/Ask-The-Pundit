
chrome.commands.onCommand.addListener((command) => {
  if (command !== "toggle-pandit") {
    return;
  }

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const activeTab = tabs && tabs[0];
    if (!activeTab || typeof activeTab.id !== "number") {
      return;
    }

    chrome.tabs.sendMessage(
      activeTab.id,
      { type: "toggle-pandit" },
      () => {
        if (chrome.runtime.lastError) {
          console.debug(
            "Ask the Pandit shortcut message was not delivered:",
            chrome.runtime.lastError.message
          );
        }
      }
    );
  });
});

chrome.action.onClicked.addListener((tab) => {
  if (tab.id) {
    chrome.tabs.sendMessage(
      tab.id,
      { type: "toggle-pandit" },
      () => {
        if (chrome.runtime.lastError) {
          console.debug("Click to toggle failed:", chrome.runtime.lastError.message);
        }
      }
    );
  }
});
