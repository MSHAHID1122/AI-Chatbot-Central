/* widget.js - Embeddable Chat Widget (vanilla JS)
   Integrates with backend /api/chat (JSON or multipart).
   Sends: { session_id, message, language, intent } or multipart form (file + same fields).
   Expects JSON response: { reply: "...", session_id?: "...", user_id?: "...", crm_id?: "..." }
*/

const API_CHAT = "/api/chat";               // must match backend route
const STORAGE_KEY = "chat_widget_session";  // same key used across widget and server dedupe if desired
const MAX_RETRIES = 4;                      // client-side 429 retry attempts

/* ----------------- Helpers ----------------- */
function getToken() {
  const meta = document.querySelector('meta[name="chat-widget-token"]');
  if (meta && meta.content) return meta.content;
  if (window.CHAT_WIDGET_TOKEN) return window.CHAT_WIDGET_TOKEN;
  return null;
}

function genSessionId() {
  return 'sess-' + Math.random().toString(36).slice(2,10);
}

function getSession() {
  let s = localStorage.getItem(STORAGE_KEY);
  if (!s) {
    s = JSON.stringify({ session_id: genSessionId(), created_at: new Date().toISOString() });
    localStorage.setItem(STORAGE_KEY, s);
  }
  return JSON.parse(s);
}

/* ----------------- UI refs ----------------- */
const widget = document.getElementById("my-chat-widget");
const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("file-input");
const langSelect = document.getElementById("lang");
const quickButtons = document.querySelectorAll(".quick-btn");

let session = getSession();
let inFlight = false;

/* ----------------- UI functions ----------------- */
function applyLanguage(lang) {
  if (lang === "ar") {
    widget.classList.add("rtl");
    widget.setAttribute("dir", "rtl");
    widget.setAttribute("lang", "ar");
    document.getElementById("widget-title").innerText = "الدعم";
    inputEl.placeholder = "اكتب رسالة...";
  } else {
    widget.classList.remove("rtl");
    widget.setAttribute("dir", "ltr");
    widget.setAttribute("lang", "en");
    document.getElementById("widget-title").innerText = "Support Chat";
    inputEl.placeholder = "Type a message...";
  }
}

function appendMessage({sender='bot', text='', meta=''}) {
  const div = document.createElement("div");
  div.className = "msg " + (sender === "user" ? "user" : "bot");
  div.setAttribute("role", "article");
  const textNode = document.createTextNode(text);
  div.appendChild(textNode);
  if (meta) {
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.innerText = meta;
    div.appendChild(metaEl);
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ----------------- Network helpers ----------------- */
async function fetchWithRetry(url, opts = {}, attempt = 0){
  const token = getToken();
  if (!opts.headers) opts.headers = {};
  opts.headers["X-Client-Session"] = session.session_id;
  if (token && !opts.headers["Authorization"]) opts.headers["Authorization"] = "Bearer " + token;

  const resp = await fetch(url, opts);
  if (resp.status === 429 && attempt < MAX_RETRIES) {
    const ra = resp.headers.get("Retry-After");
    const waitMs = ra ? parseInt(ra, 10) * 1000 : (Math.pow(2, attempt) * 500);
    await new Promise(r => setTimeout(r, waitMs));
    return fetchWithRetry(url, opts, attempt + 1);
  }
  return resp;
}

/* ----------------- Main send flow ----------------- */
async function sendMessageToServer(messageText, file = null, intent = null) {
  if (inFlight) {
    appendMessage({sender:'bot', text:"Please wait — processing previous message."});
    return;
  }
  if (!messageText && !file) {
    inputEl.focus();
    return;
  }

  inFlight = true;
  appendMessage({sender:'user', text: messageText || (file && file.name) || ''});

  try {
    let resp;
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("session_id", session.session_id);
      fd.append("message", messageText || "");
      fd.append("language", langSelect.value || "en");
      if (intent) fd.append("intent", intent);
      const headers = {}; // fetchWithRetry will attach Authorization and X-Client-Session
      resp = await fetchWithRetry(API_CHAT, { method: "POST", body: fd, headers });
    } else {
      const headers = { "Content-Type": "application/json" };
      const body = {
        session_id: session.session_id,
        message: messageText,
        language: langSelect.value || "en",
        intent: intent || null
      };
      resp = await fetchWithRetry(API_CHAT, { method: "POST", headers, body: JSON.stringify(body) });
    }

    let data;
    try { data = await resp.json(); } catch (e) { data = {}; }

    if (resp.ok) {
      const reply = data.reply || "No reply from server";
      appendMessage({sender:'bot', text: reply});
      // update session if backend returned a canonical session_id or user mappings
      if (data.session_id && data.session_id !== session.session_id) {
        session.session_id = data.session_id;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      }
    } else {
      const errText = data.error || resp.statusText || `HTTP ${resp.status}`;
      appendMessage({sender:'bot', text: `Error: ${errText}`});
    }
  } catch (err) {
    console.error("sendMessageToServer error", err);
    appendMessage({sender:'bot', text: "Network error — please try again."});
  } finally {
    inFlight = false;
  }
}

/* ----------------- Events ----------------- */
applyLanguage(langSelect.value);

sendBtn.addEventListener("click", () => {
  const file = fileInput.files[0] || null;
  const text = inputEl.value.trim();
  if (!text && !file) { inputEl.focus(); return; }
  sendMessageToServer(text, file, null);
  inputEl.value = "";
  fileInput.value = "";
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});

langSelect.addEventListener("change", (e) => { applyLanguage(e.target.value); });

// Quick intents
quickButtons.forEach(btn => btn.addEventListener("click", () => {
  const intent = btn.dataset.intent;
  const map = {
    inspiration: langSelect.value === "ar" ? "أريد إلهامًا" : "Show me product inspiration",
    faq: langSelect.value === "ar" ? "لدي سؤال عن المقاسات والمرتجعات" : "I have a question about sizes and returns",
    complaint: langSelect.value === "ar" ? "أريد تقديم شكوى" : "I want to file a complaint"
  };
  const text = map[intent] || intent;
  sendMessageToServer(text, null, intent);
}));

// optional: auto-switch UI to Arabic if user types Arabic chars
inputEl.addEventListener("input", (e) => {
  const val = e.target.value;
  const arabicRe = /[\u0600-\u06FF\u0750-\u077F]/;
  if (arabicRe.test(val) && langSelect.value !== "ar") {
    langSelect.value = "ar";
    applyLanguage("ar");
  }
});

/* Initial greeting from bot */
appendMessage({sender:'bot', text: langSelect.value === "ar" ? "مرحباً! كيف أستطيع مساعدتك؟" : "Hello! How can I help you today?"});

/* Expose programmatic API for host pages */
window.ChatWidget = {
  send: (opts) => sendMessageToServer(opts.message || "", opts.file || null, opts.intent || null),
  getSession: () => session
};