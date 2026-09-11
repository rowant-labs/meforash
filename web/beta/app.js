"use strict";

const loginView = document.querySelector("#login-view");
const chatView = document.querySelector("#chat-view");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const loginMessage = document.querySelector("#login-message");
const chatForm = document.querySelector("#chat-form");
const question = document.querySelector("#question");
const sendButton = document.querySelector("#send-button");
const requestState = document.querySelector("#request-state");
const conversation = document.querySelector("#conversation");
const welcome = document.querySelector("#welcome");
const serviceDetails = document.querySelector("#service-details");
const logoutButton = document.querySelector("#logout-button");
const newChatButton = document.querySelector("#new-chat-button");
const sourcesButton = document.querySelector("#sources-button");
const sourcesDrawer = document.querySelector("#sources-drawer");
const closeSources = document.querySelector("#close-sources");
const sourceCards = document.querySelector("#source-cards");
const sourceNotes = document.querySelector("#source-notes");

let messages = [];
let latestSources = [];
let latestSourceNotes = [];
let stateEpoch = 0;

function removeChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

async function api(path, options = {}, sessionRequired = true) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });
  let body = null;
  try {
    body = await response.json();
  } catch (_error) {
    body = { error: { code: "invalid_response", message: "The beta returned an unreadable response." } };
  }
  if (response.status === 401 && sessionRequired) throw new Error("session_expired");
  if (!response.ok) {
    const error = new Error(body?.error?.code || "request_failed");
    error.userMessage = body?.error?.message || "The beta could not accept this request.";
    throw error;
  }
  return body;
}

function resetConversation() {
  stateEpoch += 1;
  messages = [];
  latestSources = [];
  latestSourceNotes = [];
  removeChildren(conversation);
  removeChildren(sourceCards);
  removeChildren(sourceNotes);
  if (sourcesDrawer.open) sourcesDrawer.close();
  sourcesButton.hidden = true;
  welcome.hidden = false;
  requestState.textContent = "Ready";
  sendButton.disabled = false;
  question.disabled = false;
  question.value = "";
  return stateEpoch;
}

function showLogin(message = "") {
  const epoch = resetConversation();
  loginView.hidden = false;
  chatView.hidden = true;
  logoutButton.hidden = true;
  newChatButton.hidden = true;
  loginButton.disabled = false;
  loginMessage.textContent = message;
  loginForm.reset();
  document.querySelector("#invite-id").focus();
  return epoch;
}

function showChat(status) {
  loginView.hidden = true;
  chatView.hidden = false;
  logoutButton.hidden = false;
  newChatButton.hidden = false;
  loginMessage.textContent = "";
  renderStatus(status);
  question.focus();
}

function detail(term, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = value;
  serviceDetails.append(dt, dd);
}

function renderStatus(status) {
  removeChildren(serviceDetails);
  detail("Model", status.public_model || "Meforash 0.1");
  detail("Source collection", `${Number(status.source_count || 0).toLocaleString()} passage records available`);
  detail("Conversation text", status.conversation_storage === "not_stored" ? "Kept in memory for this session" : "Storage status unavailable");
  if (status.usage?.uncertain_requests) {
    detail("Usage note", `${status.usage.uncertain_requests} earlier request(s) have uncertain cost and remain reserved`);
  }
}

function appendPlainText(parent, text) {
  if (!text) return;
  const span = document.createElement("span");
  span.textContent = text;
  parent.append(span);
}

function appendInlineText(parent, text) {
  // Only a small, fixed set of presentational markers is recognized. Everything
  // else, including links, images, and raw HTML, stays visible as plain text.
  const marker = /(\*\*|__|`|\*)(.+?)\1/g;
  let offset = 0;
  for (const match of text.matchAll(marker)) {
    appendPlainText(parent, text.slice(offset, match.index));
    const tagName = match[1] === "`" ? "code" : match[1] === "*" ? "em" : "strong";
    const element = document.createElement(tagName);
    element.textContent = match[2];
    parent.append(element);
    offset = match.index + match[0].length;
  }
  appendPlainText(parent, text.slice(offset));
}

function answerBlock(parent, tagName, lines) {
  const block = document.createElement(tagName);
  lines.forEach((line, index) => {
    if (index) block.append(document.createElement("br"));
    appendInlineText(block, line);
  });
  parent.append(block);
}

function renderAnswer(parent, text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  for (let index = 0; index < lines.length;) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }
    const heading = lines[index].match(/^\s*#{1,3}\s+(.+)$/);
    if (heading) {
      answerBlock(parent, "h3", [heading[1]]);
      index += 1;
      continue;
    }
    const unordered = lines[index].match(/^\s*[-+*]\s+(.+)$/);
    const ordered = lines[index].match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const list = document.createElement(ordered ? "ol" : "ul");
      const pattern = ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-+*]\s+(.+)$/;
      while (index < lines.length) {
        const itemMatch = lines[index].match(pattern);
        if (!itemMatch) break;
        const item = document.createElement("li");
        appendInlineText(item, itemMatch[1]);
        list.append(item);
        index += 1;
      }
      parent.append(list);
      continue;
    }
    // Even an empty heading/list marker must consume a line and stay inert.
    const paragraph = [lines[index++]];
    while (index < lines.length && lines[index].trim()
      && !/^\s*#{1,3}\s+/.test(lines[index])
      && !/^\s*[-+*]\s+/.test(lines[index])
      && !/^\s*\d+[.)]\s+/.test(lines[index])) {
      paragraph.push(lines[index]);
      index += 1;
    }
    answerBlock(parent, "p", paragraph);
  }
}

function messageNode(role, text, extraClass = "") {
  const article = document.createElement("article");
  article.className = `message message-${role} ${extraClass}`.trim();
  const label = document.createElement("p");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "Meforash";
  const content = document.createElement("div");
  content.className = "message-content";
  if (role === "assistant" && !extraClass) renderAnswer(content, text);
  else content.textContent = text;
  article.append(label, content);
  conversation.append(article);
  welcome.hidden = true;
  article.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return article;
}

function safeSourceUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" && parsed.hostname === "github.com" && !parsed.username && !parsed.password
      ? parsed.href : null;
  } catch (_error) {
    return null;
  }
}

function renderSources(sources, notes) {
  latestSources = Array.isArray(sources) ? sources : [];
  latestSourceNotes = Array.isArray(notes) ? notes : [];
  removeChildren(sourceCards);
  removeChildren(sourceNotes);
  for (const source of latestSources) {
    const card = document.createElement("article");
    card.className = "source-card";
    const title = document.createElement("h3");
    title.textContent = source.reference || "Supplied passage";
    card.append(title);
    if (typeof source.requested_reference === "string" && source.requested_reference && source.requested_reference !== source.reference) {
      const reference = document.createElement("p");
      reference.className = "source-reference-note";
      reference.textContent = `Requested: ${source.requested_reference}. This edition: ${source.reference || "supplied passage"}.`;
      card.append(reference);
    }
    if (typeof source.numbering === "string" && source.numbering) {
      const numbering = document.createElement("p");
      numbering.className = "source-numbering";
      numbering.textContent = source.numbering;
      card.append(numbering);
    }
    const languageKey = typeof source.language === "string" ? source.language.toLowerCase() : "";
    const languageNames = { he: "Hebrew", heb: "Hebrew", hbo: "Hebrew", hebrew: "Hebrew", arc: "Aramaic", aramaic: "Aramaic", grc: "Greek", el: "Greek", greek: "Greek" };
    const meta = document.createElement("p");
    meta.className = "source-meta";
    meta.textContent = [source.edition, languageNames[languageKey] || source.language].filter(Boolean).join(" · ");
    const text = document.createElement("p");
    text.className = "source-text";
    text.textContent = source.text || "";
    text.dir = ["he", "heb", "hbo", "hebrew", "arc", "aramaic"].includes(languageKey) ? "rtl" : "auto";
    text.lang = ["he", "heb", "hbo", "hebrew"].includes(languageKey) ? "he" : ["grc", "el", "greek"].includes(languageKey) ? "el" : ["arc", "aramaic"].includes(languageKey) ? "arc" : languageKey;
    const attribution = document.createElement("p");
    attribution.className = "source-attribution";
    attribution.textContent = source.attribution || "";
    card.append(meta, text);
    const editorialNotes = Array.isArray(source.editorial_notes) ? source.editorial_notes.filter((note) => note && typeof note.kind === "string" && typeof note.status === "string") : [];
    if ((typeof source.editorial_status === "string" && source.editorial_status) || editorialNotes.length) {
      const editorial = document.createElement("div");
      editorial.className = "source-editorial";
      const statuses = { supplement_only: "Supplemental text, separate from the main reading", main_with_doubtful_wording: "Main text includes doubtful wording", double_bracketed: "Double-bracketed addition", single_bracketed: "Single-bracketed doubtful wording", doubtful: "Doubtful wording", main: "Main text" };
      const readable = (value) => statuses[value] || value.replace(/_/g, " ");
      if (source.editorial_status) {
        const status = document.createElement("p");
        status.textContent = `Text status: ${readable(source.editorial_status)}.`;
        editorial.append(status);
      }
      for (const note of editorialNotes) {
        const status = document.createElement("p");
        status.textContent = `${note.kind.replace(/_/g, " ")}: ${readable(note.status)}.`;
        editorial.append(status);
      }
      card.append(editorial);
    }
    if (source.attribution) card.append(attribution);
    const url = safeSourceUrl(source.url);
    if (url) {
      const link = document.createElement("a");
      link.className = "source-link";
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Open pinned upstream source";
      card.append(link);
    }
    sourceCards.append(card);
  }
  for (const note of latestSourceNotes) {
    if (typeof note !== "string") continue;
    const item = document.createElement("p");
    item.textContent = note;
    sourceNotes.append(item);
  }
  sourcesButton.hidden = latestSources.length === 0 && latestSourceNotes.length === 0;
}

function setWorking(working, label = "Ready") {
  sendButton.disabled = working;
  question.disabled = working;
  requestState.textContent = label;
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function poll(requestId, generation) {
  for (;;) {
    await delay(900);
    if (generation !== stateEpoch) return;
    try {
      const result = await api(`/api/chat/${encodeURIComponent(requestId)}`);
      if (generation !== stateEpoch) return;
      if (result.status === "running") {
        requestState.textContent = "Meforash is preparing an answer…";
        continue;
      }
      if (result.status === "complete") {
        const answer = typeof result.answer === "string" ? result.answer : "The beta returned no readable answer.";
        messages.push({ role: "assistant", content: answer });
        messageNode("assistant", answer);
        if (result.complete === false) {
          messageNode("assistant", "This response may be incomplete because generation ended before a verified stop.", "message-note");
        }
        renderSources(result.sources, result.source_notes);
        setWorking(false);
        question.focus();
        return;
      }
      throw Object.assign(new Error("generation_unavailable"), {
        userMessage: result.error?.message || "The beta could not finish this request. It was not retried.",
      });
    } catch (error) {
      if (generation !== stateEpoch) return;
      if (error.message === "session_expired") {
        showLogin("Your session has ended. Sign in again.");
        return;
      }
      messageNode("assistant", error.userMessage || "The answer is no longer available. It was not retried.", "message-error");
      setWorking(false);
      return;
    }
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (loginButton.disabled) return;
  const epoch = ++stateEpoch;
  loginButton.disabled = true;
  loginMessage.textContent = "Signing in…";
  const inviteId = document.querySelector("#invite-id").value;
  const inviteSecret = document.querySelector("#invite-secret").value;
  try {
    await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ invite_id: inviteId, invite_secret: inviteSecret }),
    }, false);
    if (epoch !== stateEpoch) return;
    loginForm.reset();
    const status = await api("/api/status");
    if (epoch !== stateEpoch) return;
    showChat(status);
  } catch (error) {
    if (epoch !== stateEpoch) return;
    if (error.message === "session_expired") showLogin("Your session has ended. Sign in again.");
    else loginMessage.textContent = error.userMessage || "Invitation credentials were not accepted.";
  }
  if (epoch === stateEpoch) loginButton.disabled = false;
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (!text || sendButton.disabled) return;
  const epoch = ++stateEpoch;
  const pendingMessages = [...messages, { role: "user", content: text }];
  setWorking(true, "Submitting securely…");
  try {
    const accepted = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ messages: pendingMessages }),
    });
    if (epoch !== stateEpoch) return;
    messages = pendingMessages;
    question.value = "";
    messageNode("user", text);
    requestState.textContent = "Meforash is preparing an answer…";
    await poll(accepted.request_id, epoch);
  } catch (error) {
    if (epoch !== stateEpoch) return;
    if (error.message === "session_expired") return showLogin("Your session has ended. Sign in again.");
    requestState.textContent = error.userMessage || "The request could not be accepted.";
    setWorking(false, requestState.textContent);
  }
});

logoutButton.addEventListener("click", async () => {
  const epoch = showLogin("Signing out…");
  // Keep a new login from racing the logout response that clears the cookie.
  loginButton.disabled = true;
  try {
    await api("/api/logout", { method: "POST", body: "{}" }, false);
    if (epoch !== stateEpoch) return;
  } catch (error) {
    if (epoch !== stateEpoch) return;
    loginButton.disabled = false;
    if (error.message === "session_expired" || error.message === "unauthorized") {
      loginMessage.textContent = "Your session has ended. Sign in again.";
      return;
    }
    loginMessage.textContent = "Sign-out could not be confirmed. Sign in again to continue.";
    return;
  }
  loginButton.disabled = false;
  loginMessage.textContent = "Signed out. Conversation history was cleared from this page.";
});

newChatButton.addEventListener("click", () => {
  resetConversation();
  question.focus();
});

sourcesButton.addEventListener("click", () => sourcesDrawer.showModal());
closeSources.addEventListener("click", () => sourcesDrawer.close());
sourcesDrawer.addEventListener("click", (event) => {
  if (event.target === sourcesDrawer) sourcesDrawer.close();
});

const initialEpoch = stateEpoch;
api("/api/status", {}, false)
  .then((status) => {
    if (initialEpoch === stateEpoch) showChat(status);
  })
  .catch((error) => {
    if (initialEpoch === stateEpoch && error.message !== "session_expired") showLogin("Sign in to begin.");
  });
