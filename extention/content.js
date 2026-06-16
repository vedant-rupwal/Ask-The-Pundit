(function () {
  const oldRoot = document.getElementById("ask-the-pandit-root");
  if (oldRoot) {
    oldRoot.remove(); 
  }

  const STORAGE_KEYS = {
    chatHistory: "askThePanditChatHistory",
    isMinimized: "askThePanditIsMinimized",
    serverUrl: "askThePanditServerUrl",
    bookFilter: "askThePanditBookFilter",
  };
  const MAX_VISIBLE_TEXT_CHARS = 6000;
  const DEFAULT_SERVER_URL = "https://vedantrupwal-ask-the-pandit.hf.space";
  const DEFAULT_BOOK_FILTER = "";

  const host = document.createElement("div");
  host.id = "ask-the-pandit-root";
  document.body.appendChild(host);

  const shadowRoot = host.attachShadow({ mode: "open" });

  shadowRoot.innerHTML = `
    <style>
      :host {
        all: initial;
      }

      .widget {
        position: fixed;
        right: 20px;
        bottom: 20px;
        z-index: 2147483647;
        font-family: Arial, Helvetica, sans-serif;
        color: #1f2937;
      }

      .panel {
        width: 360px;
        height: 520px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        background: #ffffff;
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 20px;
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.18);
        transition:
          width 0.25s ease,
          height 0.25s ease,
          transform 0.25s ease,
          border-radius 0.25s ease,
          box-shadow 0.25s ease,
          opacity 0.25s ease;
      }

      .panel.minimized {
        width: 180px;
        height: 52px;
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16);
      }

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        padding: 14px 16px;
        background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
        color: #fffdf7;
      }

      .title-wrap {
        min-width: 0;
      }

      .title {
        font-size: 15px;
        font-weight: 700;
        line-height: 1.2;
      }

      .subtitle {
        margin-top: 2px;
        font-size: 12px;
        opacity: 0.9;
      }

      .header-actions {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .clear-button,
      .toggle-button {
        border: 0;
        color: #ffffff;
        cursor: pointer;
        transition: background 0.2s ease, transform 0.2s ease;
      }

      .clear-button {
        padding: 8px 10px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.16);
        font-size: 12px;
        font-weight: 600;
      }

      .clear-button:hover,
      .toggle-button:hover {
        background: rgba(255, 255, 255, 0.28);
        transform: scale(1.04);
      }

      .toggle-button {
        background: rgba(255, 255, 255, 0.18);
        width: 34px;
        height: 34px;
        border-radius: 999px;
        font-size: 18px;
        line-height: 1;
      }

      .body {
        flex: 1;
        display: flex;
        flex-direction: column;
        min-height: 0;
        background:
          radial-gradient(circle at top left, rgba(251, 191, 36, 0.12), transparent 38%),
          linear-gradient(180deg, #fffdf8 0%, #fffaf2 100%);
        transition: opacity 0.2s ease, visibility 0.2s ease;
      }

      .messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .book-filter-wrap {
        padding: 14px 16px 0;
      }

      .multi-select {
        position: relative;
        width: 100%;
        font-size: 14px;
        user-select: none;
      }

      .multi-select-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid rgba(15, 23, 42, 0.12);
        border-radius: 14px;
        padding: 10px 12px;
        background: #ffffff;
        cursor: pointer;
        color: #1f2937;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
      }

      .multi-select-header:hover {
        border-color: rgba(249, 115, 22, 0.65);
      }

      .multi-select.open .multi-select-header {
        border-color: rgba(249, 115, 22, 0.65);
        box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.14);
      }

      .multi-select-options {
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        margin-top: 6px;
        background: #ffffff;
        border: 1px solid rgba(15, 23, 42, 0.12);
        border-radius: 14px;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
        z-index: 10;
        display: none;
        flex-direction: column;
        padding: 8px;
        max-height: 180px;
        overflow-y: auto;
      }

      .multi-select.open .multi-select-options {
        display: flex;
      }

      .checkbox-label {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 10px;
        cursor: pointer;
        border-radius: 8px;
        transition: background 0.2s ease;
      }

      .checkbox-label:hover {
        background: rgba(249, 115, 22, 0.08);
      }

      .checkbox-label input {
        accent-color: #f97316;
        width: 16px;
        height: 16px;
        cursor: pointer;
      }

      .checkbox-label input:indeterminate {
        accent-color: #f97316;
      }

      .message {
        max-width: 88%;
        padding: 12px 14px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.45;
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
        white-space: pre-wrap;
      }

      .message.assistant {
        align-self: flex-start;
        background: #fff7e6;
        color: #7c2d12;
      }

      .message.user {
        align-self: flex-end;
        background: #ffffff;
        color: #1f2937;
      }

      .message.loading {
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }

      .loading-dots {
        display: inline-flex;
        gap: 4px;
      }

      .loading-dots span {
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: currentColor;
        opacity: 0.35;
        animation: ask-the-pandit-bounce 1s infinite ease-in-out;
      }

      .loading-dots span:nth-child(2) {
        animation-delay: 0.15s;
      }

      .loading-dots span:nth-child(3) {
        animation-delay: 0.3s;
      }

      .composer {
        display: flex;
        gap: 10px;
        padding: 14px 16px 16px;
        border-top: 1px solid rgba(15, 23, 42, 0.08);
        background: rgba(255, 255, 255, 0.82);
        backdrop-filter: blur(8px);
      }

      .input {
        flex: 1;
        border: 1px solid rgba(15, 23, 42, 0.12);
        border-radius: 14px;
        padding: 11px 13px;
        font-size: 14px;
        outline: none;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
      }

      .input:focus {
        border-color: rgba(249, 115, 22, 0.65);
        box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.14);
      }

      .send-button {
        border: 0;
        border-radius: 14px;
        padding: 0 16px;
        background: #f97316;
        color: #ffffff;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.2s ease, transform 0.2s ease;
      }

      .send-button:hover {
        background: #ea580c;
        transform: translateY(-1px);
      }

      .input:disabled,
      .send-button:disabled {
        cursor: not-allowed;
        opacity: 0.65;
      }

      .send-button:disabled:hover {
        background: #f97316;
        transform: none;
      }

      .panel.minimized .body {
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
      }

      .panel.minimized .header {
        padding: 9px 12px;
      }

      .panel.minimized .title {
        font-size: 13px;
      }

      .panel.minimized .subtitle,
      .panel.minimized .clear-button {
        display: none;
      }

      .panel.minimized .book-filter-wrap {
        display: none;
      }

      .panel.minimized .toggle-button {
        width: 30px;
        height: 30px;
      }

      @media (max-width: 480px) {
        .widget {
          right: 12px;
          left: 12px;
          bottom: 12px;
        }

        .panel {
          width: auto;
          height: 70vh;
        }

        .panel.minimized {
          width: 170px;
          height: 50px;
        }
      }

      @keyframes ask-the-pandit-bounce {
        0%,
        80%,
        100% {
          opacity: 0.3;
          transform: translateY(0);
        }

        40% {
          opacity: 1;
          transform: translateY(-3px);
        }
      }
    </style>

    <div class="widget">
      <div class="panel minimized" id="panel">
        <div class="header">
          <div class="title-wrap">
            <div class="title">Ask the Pandit</div>
            <div class="subtitle">Scriptural guidance on this page</div>
          </div>
          <div class="header-actions">
            <button class="clear-button" id="clearButton" type="button">Clear Chat</button>
            <button class="toggle-button" id="toggleButton" type="button" aria-label="Expand chat">
              +
            </button>
          </div>
        </div>

        <div class="body">
          <div class="book-filter-wrap">
            <div class="multi-select" id="multiSelect">
              <div class="multi-select-header" id="multiSelectHeader">
                <span id="multiSelectLabel">All Books</span>
                <span style="font-size: 10px;">▼</span>
              </div>
              <div class="multi-select-options" id="multiSelectOptions">
                <label class="checkbox-label"><input type="checkbox" id="selectAllCheckbox"> Select All Books</label>
                <hr style="margin: 8px 0; border: none; border-top: 1px solid rgba(15, 23, 42, 0.08);">
                <label class="checkbox-label"><input type="checkbox" value="Bhagavad-gita"> Bhagavad-gita</label>
                <label class="checkbox-label"><input type="checkbox" value="Srimad-Bhagavatam"> Srimad-Bhagavatam</label>
                <label class="checkbox-label"><input type="checkbox" value="Sri Isopanisad"> Sri Isopanisad</label>
                <label class="checkbox-label"><input type="checkbox" value="Teachings of Lord Kapila"> Teachings of Lord Kapila</label>
                <label class="checkbox-label"><input type="checkbox" value="Teachings of Queen Kunti"> Teachings of Queen Kunti</label>
                <label class="checkbox-label"><input type="checkbox" value="Nector of Instuction"> Nector of Instuction</label>
                <label class="checkbox-label"><input type="checkbox" value="Nector of Devotion"> Nector of Devotion</label>
                <label class="checkbox-label"><input type="checkbox" value="Teachings of Lord Caitanya"> Teachings of Lord Caitanya</label>
                <label class="checkbox-label"><input type="checkbox" value="The Science of Self-Realization"> The Science of Self-Realization</label>
                <label class="checkbox-label"><input type="checkbox" value="Beyond Birth and Death"> Beyond Birth and Death</label>
                <label class="checkbox-label"><input type="checkbox" value="Bhakti: The Art of Eternal Love"> Bhakti: The Art of Eternal Love</label>
                <label class="checkbox-label"><input type="checkbox" value="On the Way to Kṛṣṇa"> On the Way to Kṛṣṇa</label>
                <label class="checkbox-label"><input type="checkbox" value="The Perfection of Yoga"> The Perfection of Yoga</label>
                <label class="checkbox-label"><input type="checkbox" value="Perfect Questions, Perfect Answers"> Perfect Questions, Perfect Answers</label>
                <label class="checkbox-label"><input type="checkbox" value="A Second Chance"> A Second Chance</label>
                <label class="checkbox-label"><input type="checkbox" value="The Journey of Self-Discovery"> The Journey of Self-Discovery</label>
                <label class="checkbox-label"><input type="checkbox" value="Rāja-vidyā: The King of Knowledge"> Rāja-vidyā: The King of Knowledge</label>
                <label class="checkbox-label"><input type="checkbox" value="Kṛṣṇa, the Supreme Personality of Godhead"> Kṛṣṇa, the Supreme Personality of Godhead</label>
              </div>
            </div>
          </div>

          <div class="messages" id="messages"></div>

          <div class="composer">
            <input
              class="input"
              id="messageInput"
              type="text"
              placeholder="Type your question..."
            />
            <button class="send-button" id="sendButton" type="button">Send</button>
          </div>
        </div>
      </div>
    </div>
  `;

  const panel = shadowRoot.getElementById("panel");
  const toggleButton = shadowRoot.getElementById("toggleButton");
  const clearButton = shadowRoot.getElementById("clearButton");
  const multiSelect = shadowRoot.getElementById("multiSelect");
  const multiSelectHeader = shadowRoot.getElementById("multiSelectHeader");
  const multiSelectLabel = shadowRoot.getElementById("multiSelectLabel");
  const selectAllCheckbox = shadowRoot.getElementById("selectAllCheckbox");
  const individualCheckboxes = shadowRoot.querySelectorAll(".multi-select-options input[type='checkbox']:not(#selectAllCheckbox)");
  const checkboxes = shadowRoot.querySelectorAll(".multi-select-options input[type='checkbox']");
  const messageInput = shadowRoot.getElementById("messageInput");
  const sendButton = shadowRoot.getElementById("sendButton");
  const messages = shadowRoot.getElementById("messages");

  multiSelectHeader.addEventListener("click", () => {
    multiSelect.classList.toggle("open");
  });

  selectAllCheckbox.addEventListener("change", () => {
    individualCheckboxes.forEach(cb => {
      cb.checked = selectAllCheckbox.checked;
    });
    updateBookFilter();
  });

  individualCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const allChecked = Array.from(individualCheckboxes).every(cb => cb.checked);
      const anyChecked = Array.from(individualCheckboxes).some(cb => cb.checked);
      selectAllCheckbox.checked = allChecked;
      selectAllCheckbox.indeterminate = anyChecked && !allChecked;
      
      updateBookFilter();
    });
  });

  function updateBookFilter() {
    const selected = Array.from(individualCheckboxes)
      .filter(cb => cb.checked)
      .map(cb => cb.value);

    bookFilter = selected.length === individualCheckboxes.length ? "" : selected.join(","); 
    
    if (selected.length === 0) {
      multiSelectLabel.textContent = "All Books";
    } else if (selected.length === individualCheckboxes.length) {
      multiSelectLabel.textContent = "All Books Selected";
    } else if (selected.length === 1) {
      multiSelectLabel.textContent = selected[0];
    } else {
      multiSelectLabel.textContent = `${selected.length} books selected`;
    }
    
    void persistBookFilter();
  }

  let isMinimized = true;
  let chatHistory = [];
  let serverUrl = DEFAULT_SERVER_URL;
  let bookFilter = DEFAULT_BOOK_FILTER;

  function storageAvailable() {
    return (
      typeof chrome !== "undefined" &&
      chrome.storage &&
      chrome.storage.local
    );
  }

  function storageGet(keys) {
    return new Promise((resolve) => {
      if (!storageAvailable()) {
        resolve({});
        return;
      }

      chrome.storage.local.get(keys, (items) => {
        if (chrome.runtime && chrome.runtime.lastError) {
          console.error("Ask the Pandit storage get failed:", chrome.runtime.lastError);
          resolve({});
          return;
        }

        resolve(items || {});
      });
    });
  }

  function storageSet(values) {
    return new Promise((resolve) => {
      if (!storageAvailable()) {
        resolve();
        return;
      }

      chrome.storage.local.set(values, () => {
        if (chrome.runtime && chrome.runtime.lastError) {
          console.error("Ask the Pandit storage set failed:", chrome.runtime.lastError);
        }

        resolve();
      });
    });
  }

  function storageRemove(keys) {
    return new Promise((resolve) => {
      if (!storageAvailable()) {
        resolve();
        return;
      }

      chrome.storage.local.remove(keys, () => {
        if (chrome.runtime && chrome.runtime.lastError) {
          console.error("Ask the Pandit storage remove failed:", chrome.runtime.lastError);
        }

        resolve();
      });
    });
  }

  function renderMessage(role, text) {
    const message = document.createElement("div");
    message.className = `message ${role}`;
    message.textContent = text;
    messages.appendChild(message);
    return message;
  }

  function renderLoadingMessage() {
    const phrases = [
      "Consulting the archives...",
      "Searching the Vedic scriptures...",
      "Cross-referencing the purports...",
      "Synthesizing the wisdom...",
    ];
    let phraseIndex = 0;

    const message = document.createElement("div");
    message.className = "message assistant loading";
    message.innerHTML = `
      <span class="loading-text">${phrases[phraseIndex]}</span>
      <span class="loading-dots" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </span>
    `;

    const loadingText = message.querySelector(".loading-text");
    const intervalId = window.setInterval(() => {
      phraseIndex = (phraseIndex + 1) % phrases.length;
      if (loadingText) {
        loadingText.textContent = phrases[phraseIndex];
      }
    }, 1500);

    message.dataset.loadingInterval = intervalId.toString();
    messages.appendChild(message);
    scrollMessagesToBottom();
    return message;
  }

  function clearLoadingInterval(message) {
    if (!message || !message.dataset) {
      return;
    }

    const intervalId = Number(message.dataset.loadingInterval);
    if (intervalId) {
      window.clearInterval(intervalId);
      message.dataset.loadingInterval = "";
    }
  }

  function scrollMessagesToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function renderChatHistory() {
    messages.replaceChildren();

    chatHistory.forEach((entry) => {
      renderMessage(entry.role, entry.text);
    });

    scrollMessagesToBottom();
  }

  function sanitizeChatHistory(value) {
    if (!Array.isArray(value)) {
      return [];
    }

    return value.filter((entry) => {
      return (
        entry &&
        (entry.role === "user" || entry.role === "assistant") &&
        typeof entry.text === "string"
      );
    });
  }

  function persistChatHistory() {
    return storageSet({ [STORAGE_KEYS.chatHistory]: chatHistory });
  }

  function persistMinimizedState() {
    return storageSet({ [STORAGE_KEYS.isMinimized]: isMinimized });
  }

  function persistBookFilter() {
    return storageSet({ [STORAGE_KEYS.bookFilter]: bookFilter });
  }

  function recordMessage(role, text) {
    const entry = { role, text };
    chatHistory.push(entry);
    void persistChatHistory();
  }

  function appendMessage(role, text) {
    recordMessage(role, text);
    renderMessage(role, text);
    scrollMessagesToBottom();
  }

  function setComposerDisabled(isDisabled) {
    multiSelectHeader.style.pointerEvents = isDisabled ? "none" : "auto";
    multiSelectHeader.style.opacity = isDisabled ? "0.65" : "1";
    messageInput.disabled = isDisabled;
    sendButton.disabled = isDisabled;
  }

  function focusMessageInput() {
    if (messageInput.disabled) {
      return;
    }

    messageInput.focus();
  }

  function truncateAroundCenter(text, limit) {
    if (text.length <= limit) {
      return text;
    }

    if (limit <= 5) {
      return text.slice(0, limit);
    }

    const marker = "[...]";
    const availableChars = limit - marker.length;
    const frontChars = Math.floor(availableChars / 2);
    const backChars = availableChars - frontChars;

    return `${text.slice(0, frontChars)}${marker}${text.slice(-backChars)}`;
  }

  function getVisibleText() {
    const selection = window.getSelection?.();
    if (selection) {
      const selectedText = selection.toString().trim();
      if (selectedText) {
        return truncateAroundCenter(selectedText, MAX_VISIBLE_TEXT_CHARS);
      }
    }

    let textElements = Array.from(document.querySelectorAll(".copy"));
    
    if (textElements.length === 0) {
      textElements = Array.from(document.querySelectorAll("p, article, main, h1, h2, h3, li"));
    }

    if (textElements.length === 0) {
      return "";
    }

    const relevantTexts = [];
    let currentChars = 0;

    for (const element of textElements) {
      const text = element.innerText ? element.innerText.trim() : "";
      if (!text) continue;

      const rect = element.getBoundingClientRect();
      
      if (rect.top < window.innerHeight + 500) {
        relevantTexts.push(text);
        currentChars += text.length;

        if (currentChars >= MAX_VISIBLE_TEXT_CHARS) {
          break;
        }
      }
    }

    const totalText = relevantTexts.join("\n\n");

    if (totalText.length > MAX_VISIBLE_TEXT_CHARS) {
      return totalText.slice(0, MAX_VISIBLE_TEXT_CHARS) + "\n\n[...]";
    }

    return totalText;
  }

  function updateUiState() {
    panel.classList.toggle("minimized", isMinimized);
    toggleButton.textContent = isMinimized ? "+" : "-";
    toggleButton.setAttribute(
      "aria-label",
      isMinimized ? "Expand chat" : "Minimize chat"
    );

    if (!isMinimized) {
      window.setTimeout(() => {
        focusMessageInput();
      }, 160);
    }
  }

  function togglePanel(options = {}) {
    const shouldFocusInput = Boolean(options.focusInput);
    isMinimized = !isMinimized;
    updateUiState();
    if (!isMinimized && shouldFocusInput) {
      focusMessageInput();
    }
    void persistMinimizedState();
  }

  async function clearChat() {
    chatHistory = [];
    renderChatHistory();
    await storageRemove([STORAGE_KEYS.chatHistory, STORAGE_KEYS.isMinimized]);
  }

  async function restoreState() {
    const storedState = await storageGet([
      STORAGE_KEYS.chatHistory,
      STORAGE_KEYS.isMinimized,
      STORAGE_KEYS.serverUrl,
      STORAGE_KEYS.bookFilter,
    ]);

    chatHistory = sanitizeChatHistory(storedState[STORAGE_KEYS.chatHistory]);

    if (typeof storedState[STORAGE_KEYS.isMinimized] === "boolean") {
      isMinimized = storedState[STORAGE_KEYS.isMinimized];
    }

    if (typeof storedState[STORAGE_KEYS.serverUrl] === "string") {
      const savedServerUrl = storedState[STORAGE_KEYS.serverUrl].trim();
      if (savedServerUrl) {
        serverUrl = savedServerUrl;
      }
    }

    if (typeof storedState[STORAGE_KEYS.bookFilter] === "string") {
      bookFilter = storedState[STORAGE_KEYS.bookFilter];
    }

    const savedBooks = bookFilter ? bookFilter.split(",") : [];
    const allBooksSelected = savedBooks.length === 0;
    
    if (allBooksSelected) {
      selectAllCheckbox.checked = true;
      individualCheckboxes.forEach(cb => {
        cb.checked = true;
      });
      multiSelectLabel.textContent = "All Books Selected";
    } else {
      individualCheckboxes.forEach(cb => {
        cb.checked = savedBooks.includes(cb.value);
      });
      const checkedCount = Array.from(individualCheckboxes).filter(cb => cb.checked).length;
      const allChecked = checkedCount === individualCheckboxes.length;
      selectAllCheckbox.checked = allChecked;
      selectAllCheckbox.indeterminate = !allChecked && checkedCount > 0;
      
      if (checkedCount === 1) {
        multiSelectLabel.textContent = savedBooks[0];
      } else if (checkedCount > 1) {
        multiSelectLabel.textContent = `${checkedCount} books selected`;
      } else {
        multiSelectLabel.textContent = "All Books";
      }
    }

    renderChatHistory();
    updateUiState();
  }

  async function handleSend() {
    const userQuestion = messageInput.value.trim();
    if (!userQuestion || messageInput.disabled) {
      return;
    }

    const visibleScreenText = getVisibleText();
    appendMessage("user", userQuestion);
    messageInput.value = "";
    setComposerDisabled(true);
    const thinkingMessage = renderLoadingMessage();
    let assistantMessage = null;
    let streamedText = "";
    let assistantSaved = false;

    try {
      const response = await fetch(`${serverUrl}/ask-the-pandit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_question: userQuestion,
          visible_screen_text: visibleScreenText,
          book_filter: bookFilter || null,
          history: chatHistory 
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Streaming response body is missing.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        const chunkText = decoder.decode(value, { stream: true });
        if (!chunkText) {
          continue;
        }

        if (!assistantMessage) {
          clearLoadingInterval(thinkingMessage);
          thinkingMessage.remove();
          assistantMessage = renderMessage("assistant", "");
        }

        streamedText += chunkText;
        assistantMessage.textContent = streamedText;
        scrollMessagesToBottom();
      }

      streamedText += decoder.decode();

      if (!assistantMessage) {
        clearLoadingInterval(thinkingMessage);
        thinkingMessage.remove();
        const fallbackAnswer = streamedText.trim() || "The server returned an empty answer.";
        appendMessage("assistant", fallbackAnswer);
        assistantSaved = true;
      } else {
        const finalAnswer = streamedText.trim() || "The server returned an empty answer.";
        assistantMessage.textContent = finalAnswer;
        scrollMessagesToBottom();
        recordMessage("assistant", finalAnswer);
        assistantSaved = true;
      }
    } catch (error) {
      if (thinkingMessage.isConnected) {
        clearLoadingInterval(thinkingMessage);
        thinkingMessage.remove();
      }

      if (assistantMessage && streamedText.trim()) {
        const interruptedText = `${streamedText.trim()}\n\n[Connection interrupted.]`;
        assistantMessage.textContent = interruptedText;
        scrollMessagesToBottom();
        if (!assistantSaved) {
          recordMessage("assistant", interruptedText);
          assistantSaved = true;
        }
      } else {
        appendMessage(
          "assistant",
          `I couldn't reach the Pandit server just now. Please make sure it is running on ${serverUrl}.`
        );
      }
      console.error("Ask the Pandit request failed:", error);
    } finally {
      setComposerDisabled(false);
      messageInput.focus();
    }
  }

  toggleButton.addEventListener("click", togglePanel);
  clearButton.addEventListener("click", () => {
    void clearChat();
  });
  sendButton.addEventListener("click", () => {
    void handleSend();
  });
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      void handleSend();
    }
  });

  if (
    typeof chrome !== "undefined" &&
    chrome.runtime &&
    chrome.runtime.onMessage
  ) {
    chrome.runtime.onMessage.addListener((message) => {
      if (!message || message.type !== "toggle-pandit") {
        return;
      }

      togglePanel({ focusInput: true });
    });
  }

  void restoreState();

messageInput.addEventListener("keydown", (event) => {
  event.stopPropagation();
});

messageInput.addEventListener("keypress", (event) => {
  event.stopPropagation();
});

})();
