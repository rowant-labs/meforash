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
const signInButton = document.querySelector("#sign-in-button");
const sourcesButton = document.querySelector("#sources-button");
const sourcesDrawer = document.querySelector("#sources-drawer");
const closeSources = document.querySelector("#close-sources");
const sourceCards = document.querySelector("#source-cards");
const sourceNotes = document.querySelector("#source-notes");
const quotaHint = document.querySelector("#quota-hint");
const authDialog = document.querySelector("#auth-dialog");
const authCloseButton = document.querySelector("#auth-close-button");
const authCancelButton = document.querySelector("#auth-cancel-button");
const emailForm = document.querySelector("#email-form");
const emailButton = document.querySelector("#email-button");
const authEmail = document.querySelector("#auth-email");
const codeForm = document.querySelector("#code-form");
const codeButton = document.querySelector("#code-button");
const codeEmail = document.querySelector("#code-email");
const authToken = document.querySelector("#auth-token");
const authMessage = document.querySelector("#auth-message");

let messages = [];
let latestSources = [];
let latestSourceNotes = [];
let stateEpoch = 0;
let publicAccess = false;
let emailLoginAvailable = false;
let currentAccess = { kind: "invite", questions_remaining: null, daily_limit: 20, reset_at: null };
let authReturnState = "Ready";
let authReturnWorking = false;

const HANDOFF_KEY = "meforash.auth-handoff.v1";
const HANDOFF_TTL_MS = 10 * 60 * 1000;
const HANDOFF_MAX_BYTES = 500000;

function removeChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function authHandoffStorage() {
  try {
    return window.sessionStorage || null;
  } catch (_error) {
    return null;
  }
}

function clearAuthHandoff() {
  const storage = authHandoffStorage();
  if (!storage) return;
  try {
    storage.removeItem(HANDOFF_KEY);
  } catch (_error) {
    // Storage can be unavailable without affecting the in-memory conversation.
  }
}

function boundedString(value, maximum) {
  return typeof value === "string" && value.length <= maximum ? value : null;
}

function sanitizeSource(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = {};
  const limits = {
    reference: 500, requested_reference: 500, numbering: 1000, edition: 500,
    language: 40, text: 100000, attribution: 4000, url: 4000,
    editorial_status: 100,
  };
  for (const [key, maximum] of Object.entries(limits)) {
    if (value[key] === undefined || value[key] === null) continue;
    const safe = boundedString(value[key], maximum);
    if (safe === null) return null;
    source[key] = safe;
  }
  if (value.editorial_notes !== undefined) {
    if (!Array.isArray(value.editorial_notes) || value.editorial_notes.length > 30) return null;
    source.editorial_notes = [];
    for (const note of value.editorial_notes) {
      if (!note || typeof note !== "object" || Array.isArray(note)) return null;
      const kind = boundedString(note.kind, 100);
      const status = boundedString(note.status, 100);
      if (kind === null || status === null) return null;
      source.editorial_notes.push({ kind, status });
    }
  }
  return source;
}

function sanitizeHandoff(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.version !== 1) return null;
  const now = Date.now();
  if (!Number.isFinite(value.expires_at) || value.expires_at <= now
      || value.expires_at > now + HANDOFF_TTL_MS) return null;
  if (!Array.isArray(value.messages) || value.messages.length > 40) return null;
  const safeMessages = [];
  for (const message of value.messages) {
    if (!message || typeof message !== "object" || Array.isArray(message)
        || !["user", "assistant"].includes(message.role)) return null;
    const content = boundedString(message.content, 48000);
    if (content === null) return null;
    safeMessages.push({ role: message.role, content });
  }
  const draft = boundedString(value.draft, 12000);
  if (draft === null || !Array.isArray(value.sources) || value.sources.length > 20
      || !Array.isArray(value.source_notes) || value.source_notes.length > 20) return null;
  const sources = value.sources.map(sanitizeSource);
  if (sources.some((source) => source === null)) return null;
  const notes = [];
  for (const note of value.source_notes) {
    const safe = boundedString(note, 4000);
    if (safe === null) return null;
    notes.push(safe);
  }
  return { messages: safeMessages, draft, sources, source_notes: notes };
}

function saveAuthHandoff() {
  const storage = authHandoffStorage();
  if (!storage) return;
  const expiresAt = Date.now() + HANDOFF_TTL_MS;
  const safe = sanitizeHandoff({
    version: 1,
    expires_at: expiresAt,
    messages,
    draft: question.value,
    sources: latestSources,
    source_notes: latestSourceNotes,
  });
  if (!safe) {
    clearAuthHandoff();
    return;
  }
  let value;
  try {
    value = JSON.stringify({ version: 1, expires_at: expiresAt, ...safe });
  } catch (_error) {
    clearAuthHandoff();
    return;
  }
  if (value.length > HANDOFF_MAX_BYTES) {
    clearAuthHandoff();
    return;
  }
  try {
    storage.setItem(HANDOFF_KEY, value);
  } catch (_error) {
    clearAuthHandoff();
  }
}

function readAuthHandoff() {
  const storage = authHandoffStorage();
  if (!storage) return null;
  let raw = null;
  try {
    raw = storage.getItem(HANDOFF_KEY);
  } catch (_error) {
    return null;
  }
  if (raw === null || raw.length > HANDOFF_MAX_BYTES) {
    if (raw !== null) clearAuthHandoff();
    return null;
  }
  try {
    const safe = sanitizeHandoff(JSON.parse(raw));
    if (!safe) clearAuthHandoff();
    return safe;
  } catch (_error) {
    clearAuthHandoff();
    return null;
  }
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
    error.status = response.status;
    error.userMessage = body?.error?.message || "The beta could not accept this request.";
    throw error;
  }
  return body;
}

function resetConversation() {
  stateEpoch += 1;
  clearAuthHandoff();
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
  if (authDialog.open) authDialog.close();
  loginView.hidden = false;
  chatView.hidden = true;
  logoutButton.hidden = true;
  signInButton.hidden = true;
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
  newChatButton.hidden = false;
  loginMessage.textContent = "";
  renderStatus(status);
  question.focus();
}

function formatReset(value) {
  if (typeof value !== "string" || !value) return "";
  const time = new Date(value);
  return Number.isFinite(time.getTime()) ? time.toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  }) : "";
}

function renderAccess(access) {
  if (access && typeof access === "object" && ["guest", "account", "invite"].includes(access.kind)) {
    currentAccess = {
      kind: access.kind,
      questions_remaining: Number.isInteger(access.questions_remaining) && access.questions_remaining >= 0
        ? access.questions_remaining : null,
      daily_limit: Number.isInteger(access.daily_limit) && access.daily_limit > 0 ? access.daily_limit : 20,
      reset_at: typeof access.reset_at === "string" ? access.reset_at : null,
    };
  } else if (!publicAccess) {
    currentAccess = { kind: "invite", questions_remaining: null, daily_limit: 20, reset_at: null };
  }
  const guest = publicAccess && currentAccess.kind === "guest";
  signInButton.hidden = !(guest && emailLoginAvailable);
  logoutButton.hidden = currentAccess.kind === "guest";
  quotaHint.hidden = currentAccess.kind === "invite" || currentAccess.questions_remaining === null;
  if (quotaHint.hidden) {
    quotaHint.textContent = "";
  } else if (guest) {
    quotaHint.textContent = `${currentAccess.questions_remaining} of 3 free guest questions remaining${emailLoginAvailable ? ` · Sign in free for up to ${currentAccess.daily_limit} each day.` : "."}`;
  } else {
    const reset = formatReset(currentAccess.reset_at);
    quotaHint.textContent = `${currentAccess.questions_remaining} questions remaining today${reset ? ` · Resets ${reset}` : "."}`;
  }
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
  renderAccess(status.access);
}

function restoreAuthHandoff(handoff, clear = true) {
  if (!handoff) return;
  messages = handoff.messages;
  removeChildren(conversation);
  for (const message of messages) messageNode(message.role, message.content);
  question.value = handoff.draft;
  renderSources(handoff.sources, handoff.source_notes);
  if (clear) clearAuthHandoff();
}

function resetAuthDialog() {
  emailForm.hidden = false;
  codeForm.hidden = true;
  emailButton.disabled = false;
  codeButton.disabled = false;
  authMessage.textContent = "";
  codeEmail.textContent = "";
  emailForm.reset();
  codeForm.reset();
}

function openAuthDialog(message = "") {
  if (!emailLoginAvailable) return;
  if (!authDialog.open) {
    authReturnState = requestState.textContent;
    authReturnWorking = sendButton.disabled || question.disabled;
    stateEpoch += 1;
    setWorking(false, authReturnState);
    resetAuthDialog();
    saveAuthHandoff();
    authDialog.showModal();
  }
  authMessage.textContent = message;
  authEmail.focus();
}

function cancelAuthDialog() {
  if (authDialog.open) authDialog.close();
  resetAuthDialog();
  clearAuthHandoff();
  setWorking(authReturnWorking, authReturnState);
  question.focus();
}

function showPublicGuestUnavailable(message, handoff) {
  loginView.hidden = true;
  chatView.hidden = false;
  newChatButton.hidden = true;
  logoutButton.hidden = true;
  signInButton.hidden = !emailLoginAvailable;
  loginMessage.textContent = "";
  quotaHint.hidden = false;
  quotaHint.textContent = emailLoginAvailable
    ? "Guest access is temporarily unavailable. Sign in with email to continue."
    : "Guest access is temporarily unavailable. Please try again shortly.";
  setWorking(true, message || "Guest access is temporarily unavailable.");
  restoreAuthHandoff(handoff, false);
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

async function refreshStatus(generation) {
  if (!publicAccess) return;
  try {
    const status = await api("/api/status");
    if (generation === stateEpoch) renderStatus(status);
  } catch (_error) {
    // The completed answer remains useful; the next request will enforce quota.
  }
}

async function recoverGuest(message) {
  const epoch = ++stateEpoch;
  setWorking(true, "Restoring guest access…");
  try {
    const status = await api("/api/guest", { method: "POST", body: "{}" }, false);
    if (epoch !== stateEpoch) return;
    showChat(status);
    setWorking(false, message);
  } catch (error) {
    if (epoch !== stateEpoch) return;
    showPublicGuestUnavailable(
      error.userMessage || "Guest access is temporarily unavailable.",
      null,
    );
  }
}

function dailyLimitMessage() {
  const reset = formatReset(currentAccess.reset_at);
  return `Daily question limit reached.${reset ? ` More questions will be available ${reset}.` : " Please return after the daily reset."}`;
}

async function poll(requestId, generation) {
  let progressNode = null;
  let progressAnswer = "";
  let progressRevision = 0;

  function removeProgressNode() {
    if (progressNode && progressNode.parentNode === conversation) {
      conversation.removeChild(progressNode);
    }
    progressNode = null;
  }

  function acceptProgress(answer, revision) {
    if (validProgressRevision(revision) && revision > progressRevision
        && typeof answer === "string" && answer.startsWith(progressAnswer)) {
      progressRevision = revision;
      progressAnswer = answer;
      if (answer && !progressNode) {
        progressNode = messageNode("assistant", "", "message-progress");
      }
      if (progressNode) progressNode.children[1].textContent = answer;
    }
  }

  for (;;) {
    await delay(900);
    if (generation !== stateEpoch) return;
    try {
      const result = await api(`/api/chat/${encodeURIComponent(requestId)}`);
      if (generation !== stateEpoch) return;
      if (result.status === "running") {
        acceptProgress(result.answer, result.revision);
        requestState.textContent = "Meforash is preparing an answer…";
        continue;
      }
      if (result.status === "complete") {
        const answer = typeof result.answer === "string" ? result.answer : "The beta returned no readable answer.";
        removeProgressNode();
        messages.push({ role: "assistant", content: answer });
        messageNode("assistant", answer);
        if (result.complete === false) {
          messageNode("assistant", "This response may be incomplete because generation ended before a verified stop.", "message-note");
        }
        renderSources(result.sources, result.source_notes);
        setWorking(false);
        question.focus();
        await refreshStatus(generation);
        return;
      }
      if (result.status === "error") {
        const terminalPartial = typeof result.partial_answer === "string"
          && result.partial_answer.startsWith(progressAnswer)
          ? result.partial_answer : progressAnswer;
        if (terminalPartial) {
          if (!progressNode) {
            progressNode = messageNode("assistant", "", "message-progress");
          }
          progressNode.children[1].textContent = terminalPartial;
          messageNode(
            "assistant",
            `${result.error?.message || "The beta could not finish this request. It was not retried."} The partial answer above is incomplete and will not be included in later questions.`,
            "message-error",
          );
          setWorking(false);
          await refreshStatus(generation);
          return;
        }
      }
      throw Object.assign(new Error("generation_unavailable"), {
        userMessage: result.error?.message || "The beta could not finish this request. It was not retried.",
      });
    } catch (error) {
      if (generation !== stateEpoch) return;
      if (error.message === "session_expired") {
        if (publicAccess) await recoverGuest("Your session ended. Guest access is ready.");
        else showLogin("Your session has ended. Sign in again.");
        return;
      }
      if (progressAnswer) {
        if (!progressNode) {
          progressNode = messageNode("assistant", "", "message-progress");
          progressNode.children[1].textContent = progressAnswer;
        }
        messageNode(
          "assistant",
          `${error.userMessage || "The answer is no longer available. It was not retried."} The partial answer above is incomplete and will not be included in later questions.`,
          "message-error",
        );
        setWorking(false);
        await refreshStatus(generation);
        return;
      }
      messageNode("assistant", error.userMessage || "The answer is no longer available. It was not retried.", "message-error");
      setWorking(false);
      return;
    }
  }
}

function validProgressRevision(value) {
  return Number.isInteger(value) && value >= 0;
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

signInButton.addEventListener("click", () => openAuthDialog());
authCloseButton.addEventListener("click", cancelAuthDialog);
authCancelButton.addEventListener("click", cancelAuthDialog);
authDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  cancelAuthDialog();
});

emailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (emailButton.disabled) return;
  const email = authEmail.value.trim();
  const epoch = stateEpoch;
  emailButton.disabled = true;
  authMessage.textContent = "Sending a sign-in code…";
  try {
    await api("/api/auth/start", {
      method: "POST",
      body: JSON.stringify({ email }),
    }, false);
    if (epoch !== stateEpoch || !authDialog.open) return;
    codeEmail.textContent = email;
    emailForm.hidden = true;
    codeForm.hidden = false;
    authMessage.textContent = "If the address can receive a code, it is on its way.";
    authToken.focus();
  } catch (error) {
    if (epoch !== stateEpoch || !authDialog.open) return;
    authMessage.textContent = error.userMessage || "A sign-in code could not be sent. Please try again.";
  }
  if (epoch === stateEpoch) emailButton.disabled = false;
});

codeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (codeButton.disabled) return;
  const email = authEmail.value.trim();
  const token = authToken.value.trim();
  if (!/^[0-9]{6,10}$/.test(token)) {
    authMessage.textContent = "Enter the 6–10 digit sign-in code.";
    return;
  }
  const epoch = stateEpoch;
  codeButton.disabled = true;
  authMessage.textContent = "Checking the code…";
  try {
    const status = await api("/api/auth/verify", {
      method: "POST",
      body: JSON.stringify({ email, token }),
    }, false);
    if (epoch !== stateEpoch || !authDialog.open) return;
    authDialog.close();
    clearAuthHandoff();
    resetAuthDialog();
    setWorking(false);
    showChat(status);
    question.focus();
    return;
  } catch (error) {
    if (epoch !== stateEpoch || !authDialog.open) return;
    authMessage.textContent = error.userMessage || "That sign-in code could not be verified.";
    authToken.focus();
  }
  if (epoch === stateEpoch) codeButton.disabled = false;
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
    if (error.message === "session_expired") {
      if (publicAccess) return recoverGuest("Your session ended. Guest access is ready.");
      return showLogin("Your session has ended. Sign in again.");
    }
    if (error.message === "guest_limit_reached") {
      setWorking(false, "Free guest questions used");
      if (emailLoginAvailable) {
        openAuthDialog(error.userMessage || "You have used the free guest questions. Sign in to continue.");
      } else {
        setWorking(false, error.userMessage || "The free guest questions have been used.");
      }
      return;
    }
    if (error.message === "daily_limit_reached") {
      setWorking(false, dailyLimitMessage());
      return;
    }
    requestState.textContent = error.userMessage || "The request could not be accepted.";
    setWorking(false, requestState.textContent);
  }
});

logoutButton.addEventListener("click", async () => {
  if (publicAccess && currentAccess.kind === "account") {
    const epoch = resetConversation();
    if (authDialog.open) authDialog.close();
    clearAuthHandoff();
    logoutButton.disabled = true;
    setWorking(true, "Signing out…");
    let signedOut = false;
    try {
      await api("/api/logout", { method: "POST", body: "{}" }, false);
      if (epoch !== stateEpoch) return;
      signedOut = true;
      const status = await api("/api/guest", { method: "POST", body: "{}" }, false);
      if (epoch !== stateEpoch) return;
      showChat(status);
      setWorking(false, "Signed out. Guest access is ready.");
    } catch (error) {
      if (epoch !== stateEpoch) return;
      if (signedOut) {
        showPublicGuestUnavailable(
          error.userMessage || "Signed out, but guest access is temporarily unavailable.",
          null,
        );
      } else {
        setWorking(false, error.userMessage || "Sign-out could not be confirmed. Please try again.");
      }
    }
    logoutButton.disabled = false;
    return;
  }
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
const pendingHandoff = readAuthHandoff();

async function initialize() {
  let access = null;
  try {
    access = await api("/api/access", {}, false);
  } catch (_error) {
    access = { public_access: false, email_login_available: false };
  }
  if (initialEpoch !== stateEpoch) return;
  publicAccess = access?.public_access === true;
  emailLoginAvailable = publicAccess && access?.email_login_available === true;
  if (!publicAccess) clearAuthHandoff();

  try {
    const status = await api("/api/status", {}, false);
    if (initialEpoch !== stateEpoch) return;
    showChat(status);
    if (publicAccess && status?.access?.kind === "guest") restoreAuthHandoff(pendingHandoff);
    else clearAuthHandoff();
    return;
  } catch (_error) {
    if (initialEpoch !== stateEpoch) return;
  }

  if (publicAccess) {
    try {
      const status = await api("/api/guest", { method: "POST", body: "{}" }, false);
      if (initialEpoch !== stateEpoch) return;
      showChat(status);
      if (status?.access?.kind === "guest") restoreAuthHandoff(pendingHandoff);
      else clearAuthHandoff();
      return;
    } catch (error) {
      if (initialEpoch !== stateEpoch) return;
      showPublicGuestUnavailable(
        error.userMessage || "Guest access is temporarily unavailable.",
        pendingHandoff,
      );
      return;
    }
  }
  showLogin("Sign in to begin.");
}

initialize();
