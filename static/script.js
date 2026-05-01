/**
 * Orca AI — Frontend Script
 * Handles chat, streaming responses, history, and UI state
 */

// ── State ─────────────────────────────────────────────────────
const state = {
  currentChatId: null,
  isStreaming: false,
  abortController: null,
};

// ── DOM References ─────────────────────────────────────────────
const elements = {
  chatWindow:      document.getElementById("chatWindow"),
  messages:        document.getElementById("messages"),
  welcome:         document.getElementById("welcome"),
  userInput:       document.getElementById("userInput"),
  sendBtn:         document.getElementById("sendBtn"),
  chatList:        document.getElementById("chatList"),
  newChatBtn:      document.getElementById("newChatBtn"),
  newChatMobile:   document.getElementById("newChatMobile"),
  menuBtn:         document.getElementById("menuBtn"),
  sidebar:         document.getElementById("sidebar"),
  sidebarOverlay:  document.getElementById("sidebarOverlay"),
  modelName:       document.getElementById("modelName"),
};

// ── Init ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadConfig();
  loadHistory();
  setupEventListeners();
});

// ── Configuration ─────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch("/config");
    const cfg = await res.json();
    elements.modelName.textContent = `${cfg.provider} / ${cfg.model}`;
  } catch {
    elements.modelName.textContent = "offline";
  }
}

// ── Event Listeners ───────────────────────────────────────────
function setupEventListeners() {
  // Send button
  elements.sendBtn.addEventListener("click", handleSend);

  // Enter to send (Shift+Enter for newline)
  elements.userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Auto-resize textarea & toggle send button
  elements.userInput.addEventListener("input", () => {
    autoResize(elements.userInput);
    elements.sendBtn.disabled = !elements.userInput.value.trim() || state.isStreaming;
  });

  // New chat buttons
  elements.newChatBtn.addEventListener("click", startNewChat);
  elements.newChatMobile.addEventListener("click", startNewChat);

  // Mobile sidebar toggle
  elements.menuBtn.addEventListener("click", toggleSidebar);
  elements.sidebarOverlay.addEventListener("click", closeSidebar);

  // Suggestion chips
  document.querySelectorAll(".suggestion-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      elements.userInput.value = chip.dataset.text;
      autoResize(elements.userInput);
      elements.sendBtn.disabled = false;
      elements.userInput.focus();
    });
  });
}

// ── Sidebar ───────────────────────────────────────────────────
function toggleSidebar() {
  elements.sidebar.classList.toggle("open");
  elements.sidebarOverlay.classList.toggle("visible");
}
function closeSidebar() {
  elements.sidebar.classList.remove("open");
  elements.sidebarOverlay.classList.remove("visible");
}

// ── Chat History ──────────────────────────────────────────────
async function loadHistory() {
  try {
    const res = await fetch("/history");
    const chats = await res.json();
    renderChatList(chats);
  } catch (e) {
    console.warn("Could not load history:", e);
  }
}

function renderChatList(chats) {
  elements.chatList.innerHTML = "";
  if (chats.length === 0) {
    elements.chatList.innerHTML = `<p style="padding:12px 14px;font-size:12px;color:var(--text-muted)">No chats yet</p>`;
    return;
  }
  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = "chat-item" + (chat.id === state.currentChatId ? " active" : "");
    item.dataset.id = chat.id;
    item.innerHTML = `
      <span class="chat-item-icon">💬</span>
      <span class="chat-item-title">${escapeHtml(chat.title)}</span>
      <button class="chat-item-delete" title="Delete chat" data-id="${chat.id}">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    `;
    item.addEventListener("click", (e) => {
      if (!e.target.closest(".chat-item-delete")) {
        loadChat(chat.id);
        closeSidebar();
      }
    });
    item.querySelector(".chat-item-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteChat(chat.id);
    });
    elements.chatList.appendChild(item);
  });
}

async function loadChat(chatId) {
  try {
    const res = await fetch(`/history/${chatId}`);
    const chat = await res.json();
    state.currentChatId = chatId;
    elements.messages.innerHTML = "";
    hideWelcome();
    chat.messages.forEach((msg) => {
      appendMessage(msg.role, msg.content, false);
    });
    scrollToBottom(false);
    updateActiveChatInSidebar(chatId);
  } catch (e) {
    console.error("Failed to load chat:", e);
  }
}

async function deleteChat(chatId) {
  try {
    await fetch(`/history/${chatId}`, { method: "DELETE" });
    if (chatId === state.currentChatId) {
      startNewChat();
    } else {
      loadHistory();
    }
  } catch (e) {
    console.error("Failed to delete chat:", e);
  }
}

function updateActiveChatInSidebar(chatId) {
  document.querySelectorAll(".chat-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === chatId);
  });
}

function updateChatTitle(chatId, title) {
  const item = document.querySelector(`.chat-item[data-id="${chatId}"] .chat-item-title`);
  if (item) item.textContent = title;
}

// ── New Chat ──────────────────────────────────────────────────
function startNewChat() {
  state.currentChatId = null;
  elements.messages.innerHTML = "";
  showWelcome();
  elements.userInput.value = "";
  elements.sendBtn.disabled = true;
  updateActiveChatInSidebar(null);
  elements.userInput.focus();
  closeSidebar();
}

// ── Send Message ──────────────────────────────────────────────
async function handleSend() {
  const text = elements.userInput.value.trim();
  if (!text || state.isStreaming) return;

  hideWelcome();

  // Append user message
  appendMessage("user", text, false);

  // Clear input
  elements.userInput.value = "";
  autoResize(elements.userInput);
  elements.sendBtn.disabled = true;

  // Stream assistant response
  await streamResponse(text);
}

async function streamResponse(message) {
  state.isStreaming = true;
  state.abortController = new AbortController();

  // Show stop button
  showStopButton();

  // Create assistant message bubble
  const { row, bubble } = appendMessage("assistant", "", true);
  const cursor = document.createElement("span");
  cursor.className = "typing-cursor";
  bubble.appendChild(cursor);

  let rawText = "";

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        chat_id: state.currentChatId,
      }),
      signal: state.abortController.signal,
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // Keep incomplete chunk

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));

          if (data.type === "meta") {
            // Update current chat ID from server
            state.currentChatId = data.chat_id;
            // Add to sidebar if new
            loadHistory();
          } else if (data.type === "token") {
            rawText += data.content;
            // Render markdown as we go
            bubble.innerHTML = renderMarkdown(rawText);
            bubble.appendChild(cursor);
            scrollToBottom();
          } else if (data.type === "done") {
            // Final render without cursor
            bubble.innerHTML = renderMarkdown(rawText);
            updateChatTitle(state.currentChatId, data.title);
            updateActiveChatInSidebar(state.currentChatId);
          }
        } catch { /* skip malformed line */ }
      }
    }

  } catch (err) {
    if (err.name === "AbortError") {
      bubble.innerHTML = renderMarkdown(rawText || "_Generation stopped._");
    } else {
      bubble.innerHTML = `<span style="color:#ff6b6b">⚠️ Failed to connect. Is the server running?</span>`;
      console.error("Stream error:", err);
    }
  } finally {
    // Remove cursor if still there
    const c = bubble.querySelector(".typing-cursor");
    if (c) c.remove();

    state.isStreaming = false;
    state.abortController = null;
    hideStopButton();
    elements.sendBtn.disabled = !elements.userInput.value.trim();
    scrollToBottom();
  }
}

// ── Stop Generation ───────────────────────────────────────────
function showStopButton() {
  // Replace send button with stop button
  const stop = document.createElement("button");
  stop.className = "btn-stop";
  stop.id = "stopBtn";
  stop.title = "Stop generating";
  stop.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>`;
  stop.addEventListener("click", () => {
    if (state.abortController) state.abortController.abort();
  });
  elements.sendBtn.replaceWith(stop);
}

function hideStopButton() {
  const stop = document.getElementById("stopBtn");
  if (stop) stop.replaceWith(elements.sendBtn);
}

// ── Message Rendering ─────────────────────────────────────────
function appendMessage(role, content, streaming) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const inner = document.createElement("div");
  inner.className = "message-inner";

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role}`;
  avatar.textContent = role === "user" ? "U" : "🐋";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (!streaming && content) {
    bubble.innerHTML = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);
  }
  if (role === "user" && content) {
    bubble.style.whiteSpace = "pre-wrap";
    bubble.textContent = content;
  }

  inner.appendChild(avatar);
  inner.appendChild(bubble);
  row.appendChild(inner);
  elements.messages.appendChild(row);

  scrollToBottom();
  return { row, bubble };
}

// ── Markdown Renderer ─────────────────────────────────────────
// Lightweight markdown parser — no external dependency needed
function renderMarkdown(text) {
  if (!text) return "";

  let html = escapeHtml(text);

  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`
  );

  // Inline code
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");

  // Bold **text**
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Italic *text*
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");

  // Strikethrough ~~text~~
  html = html.replace(/~~([^~]+)~~/g, "<del>$1</del>");

  // Headers
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Horizontal rule
  html = html.replace(/^---+$/gm, "<hr/>");

  // Blockquote
  html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // Unordered list items
  html = html.replace(/^[\*\-] (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g, "<ul>$1</ul>");

  // Ordered list items
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Paragraphs — convert double newlines to <p> breaks
  html = html
    .split(/\n{2,}/)
    .map((block) => {
      if (block.startsWith("<h") || block.startsWith("<pre") ||
          block.startsWith("<ul") || block.startsWith("<ol") ||
          block.startsWith("<hr") || block.startsWith("<blockquote")) {
        return block;
      }
      return `<p>${block.replace(/\n/g, "<br/>")}</p>`;
    })
    .join("");

  return html;
}

// ── Utilities ─────────────────────────────────────────────────
function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
}

function scrollToBottom(smooth = true) {
  elements.chatWindow.scrollTo({
    top: elements.chatWindow.scrollHeight,
    behavior: smooth ? "smooth" : "instant",
  });
}

function hideWelcome() {
  elements.welcome.classList.add("hidden");
}

function showWelcome() {
  elements.welcome.classList.remove("hidden");
}
