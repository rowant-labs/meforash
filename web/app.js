"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const ui = {
    main: $("main"), welcome: $("welcome"), conversation: $("conversation"),
    messages: $("messages"), form: $("chat-form"), question: $("question"),
    send: $("send"), hint: $("composer-hint"), note: $("connection-note"),
    model: $("model-label"), modelState: $("model-state"), dot: $("status-dot"),
    checkConnection: $("check-connection"), checkAnswer: $("check-answer"),
    drawer: $("sources-drawer"), cards: $("source-cards"), sourceNotes: $("source-notes"), sourceCount: $("source-count"),
    announcer: $("announcer"),
  };
  const state = { generation: 0, history: [], sources: [], sourceNotes: [], ready: false, checking: false, job: null };
  const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const announce = (message) => { ui.announcer.textContent = message; };

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  // No model or source text is interpreted as HTML. The supported formatting
  // creates elements explicitly and inserts every text fragment with textContent.
  function inline(parent, text) {
    const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/g;
    let offset = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(offset, match.index)));
      const token = match[0];
      const bold = token.startsWith("**");
      parent.append(node(bold ? "strong" : token.startsWith("`") ? "code" : "em", "", token.slice(bold ? 2 : 1, bold ? -2 : -1)));
      offset = match.index + token.length;
    }
    parent.append(document.createTextNode(text.slice(offset)));
  }

  function renderAnswer(container, text) {
    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    let index = 0;
    const isList = (line) => /^\s*(?:[-*+] |\d+[.)] )/.test(line);
    const isTableRule = (line) => /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
    const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index += 1; continue; }
      if (/^\s*```/.test(line)) {
        const code = [];
        index += 1;
        while (index < lines.length && !/^\s*```/.test(lines[index])) code.push(lines[index++]);
        if (index < lines.length) index += 1;
        const pre = node("pre"); pre.append(node("code", "", code.join("\n"))); container.append(pre);
        continue;
      }
      if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) { container.append(node("hr")); index += 1; continue; }
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      if (heading) {
        const element = node(line.startsWith("###") ? "h4" : "h3"); inline(element, heading[1]); container.append(element); index += 1; continue;
      }
      if (line.includes("|") && index + 1 < lines.length && isTableRule(lines[index + 1])) {
        const wrapper = node("div", "table-wrap");
        const table = node("table"); const head = node("thead"); const row = node("tr");
        for (const cell of cells(line)) { const th = node("th"); th.scope = "col"; inline(th, cell); row.append(th); }
        head.append(row); table.append(head); index += 2;
        const body = node("tbody");
        while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
          const tr = node("tr"); for (const cell of cells(lines[index++])) { const td = node("td"); inline(td, cell); tr.append(td); } body.append(tr);
        }
        table.append(body); wrapper.append(table); container.append(wrapper); continue;
      }
      if (isList(line)) {
        const ordered = /^\s*\d+[.)] /.test(line); const list = node(ordered ? "ol" : "ul");
        while (index < lines.length && isList(lines[index]) && /^\s*\d+[.)] /.test(lines[index]) === ordered) {
          const item = node("li"); inline(item, lines[index++].replace(/^\s*(?:[-*+] |\d+[.)] )/, "")); list.append(item);
        }
        container.append(list); continue;
      }
      if (/^>\s?/.test(line)) {
        const quoted = []; while (index < lines.length && /^>\s?/.test(lines[index])) quoted.push(lines[index++].replace(/^>\s?/, ""));
        const quote = node("blockquote"); inline(quote, quoted.join("\n")); container.append(quote); continue;
      }
      const paragraph = [line]; index += 1;
      while (index < lines.length && lines[index].trim() && !/^(?:#{1,6}\s|>\s?|\s*```)/.test(lines[index]) && !isList(lines[index]) && !/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(lines[index]) && !(lines[index].includes("|") && index + 1 < lines.length && isTableRule(lines[index + 1]))) paragraph.push(lines[index++]);
      const element = node("p"); inline(element, paragraph.join("\n")); container.append(element);
    }
  }

  function resizeComposer() {
    ui.question.style.height = "auto";
    ui.question.style.height = Math.min(190, Math.max(48, ui.question.scrollHeight)) + "px";
  }

  function refreshComposer() {
    ui.send.disabled = !state.ready || Boolean(state.job) || !ui.question.value.trim();
    ui.form.setAttribute("aria-busy", String(Boolean(state.job)));
    ui.checkConnection.hidden = state.ready || state.checking;
    ui.checkAnswer.hidden = !(state.job && state.job.paused && state.job.id);
    if (state.job) {
      const previous = state.job.generation !== state.generation;
      ui.hint.textContent = previous ? "Your new conversation is ready." : "There’s time to consider a good question.";
      ui.note.textContent = state.job.paused
        ? "The connection paused. You can check the same request without sending it again."
        : previous ? "The previous request is still finishing. Its answer won’t appear here." : "Waiting for the model’s answer. This can take a little while.";
    } else if (!state.ready) {
      ui.hint.textContent = "Your question will stay here while the model connects.";
      ui.note.textContent = state.checking ? "Checking the connection to this private preview…" : "The model isn’t available right now.";
    } else {
      ui.hint.textContent = state.history.length ? "Keep the conversation going." : "You can start wherever you are.";
      ui.note.textContent = "Chat is not saved here. Messages are sent to Tinker for answers.";
    }
  }

  async function jsonRequest(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, { cache: "no-store", credentials: "same-origin", ...options, signal: controller.signal, headers: { Accept: "application/json", ...(options.headers || {}) } });
      let payload;
      try { payload = await response.json(); } catch { throw Object.assign(new Error("Unreadable response"), { status: response.status }); }
      if (!response.ok) throw Object.assign(new Error("Request unavailable"), { status: response.status });
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("Unreadable response");
      return payload;
    } finally { clearTimeout(timeout); }
  }

  async function checkConnection() {
    if (state.checking) return;
    state.checking = true; ui.modelState.textContent = "Connecting"; ui.dot.dataset.state = "checking"; refreshComposer();
    try {
      const status = await jsonRequest("/api/status");
      state.ready = status.configured === true && status.ready !== false;
      // The interface names the retained original-language adapter, rather than
      // presenting provider names or private checkpoint identifiers.
      ui.model.textContent = "Original-language model";
      ui.modelState.textContent = state.ready ? "Ready" : "Not connected";
      ui.dot.dataset.state = state.ready ? "ready" : "unavailable";
    } catch {
      state.ready = false; ui.modelState.textContent = "Connection unavailable"; ui.dot.dataset.state = "unavailable";
    } finally { state.checking = false; refreshComposer(); }
  }

  function nearBottom() { return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 260; }
  function scrollToConversation() { $("conversation-end").scrollIntoView({ behavior: "smooth", block: "end" }); }

  function userMessage(text) {
    const message = node("article", "message message-user");
    message.setAttribute("aria-label", "Your question");
    message.append(node("div", "message-content", text)); ui.messages.append(message);
  }

  function assistantMessage() {
    const message = node("article", "message message-assistant");
    message.setAttribute("aria-label", "Original-language model response");
    const label = node("div", "message-label"); const mark = node("span", "mini-mark"); mark.setAttribute("aria-hidden", "true");
    label.append(mark, node("span", "", "Original-language model"));
    const content = node("div", "message-content"); message.append(label, content); ui.messages.append(message);
    return { message, content };
  }

  function showPending(job) {
    if (job.generation !== state.generation || !job.view.message.isConnected) return;
    job.view.content.replaceChildren();
    const pending = node("div", "pending-content");
    const light = node("span", "pending-light"); light.setAttribute("aria-hidden", "true");
    const label = node("span", "", "Waiting for the model’s answer…");
    const timer = node("span", "pending-timer", ""); timer.setAttribute("aria-hidden", "true");
    pending.append(light, label, timer); job.view.content.append(pending);
    job.timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - job.startedAt) / 1000);
      timer.textContent = seconds >= 10 ? seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s` : "";
    }, 1000);
  }

  function stopTimer(job) { if (job.timer) clearInterval(job.timer); job.timer = null; }

  function displayError(job, message, allowCheck = false) {
    if (job.generation !== state.generation || !job.view.message.isConnected) return;
    stopTimer(job); job.view.content.replaceChildren();
    const error = node("div", "error-content"); error.append(node("p", "", message));
    if (allowCheck) {
      const check = node("button", "text-button", "Check for answer"); check.type = "button"; check.addEventListener("click", () => resumeRequest(job)); error.append(check);
    } else {
      const edit = node("button", "text-button", "Edit your question"); edit.type = "button";
      edit.addEventListener("click", () => { ui.question.value = job.question; resizeComposer(); refreshComposer(); ui.question.focus(); }); error.append(edit);
    }
    job.view.content.append(error); announce(message);
  }

  function safeSources(value) {
    if (!Array.isArray(value)) return [];
    return value.filter((source) => source && typeof source === "object" && typeof source.text === "string").map((source) => ({
      id: typeof source.id === "string" ? source.id : "",
      reference: typeof source.reference === "string" ? source.reference : "Source passage",
      edition: typeof source.edition === "string" ? source.edition : "Original-language edition",
      language: typeof source.language === "string" ? source.language : "",
      text: source.text,
      url: typeof source.url === "string" ? source.url : "",
      requested_reference: typeof source.requested_reference === "string" ? source.requested_reference : "",
      numbering: typeof source.numbering === "string" ? source.numbering : "",
      editorial_status: typeof source.editorial_status === "string" ? source.editorial_status : "",
      editorial_notes: Array.isArray(source.editorial_notes) ? source.editorial_notes.filter((note) => note && typeof note === "object" && typeof note.kind === "string" && typeof note.status === "string").map((note) => ({ kind: note.kind, status: note.status })) : [],
      attribution: typeof source.attribution === "string" ? source.attribution : "",
    }));
  }

  function setSources(sources, notes = []) {
    state.sources = sources; state.sourceNotes = notes; ui.sourceCount.textContent = String(sources.length); ui.sourceCount.hidden = !sources.length;
  }

  function showSources(sources = state.sources, notes = state.sourceNotes) {
    ui.cards.replaceChildren(); ui.sourceNotes.replaceChildren();
    for (const note of notes) ui.sourceNotes.append(node("p", "", note));
    if (!sources.length) {
      const empty = node("div", "sources-empty");
      empty.append(node("strong", "", "No exact passage was supplied."), node("p", "", "An answer may draw on the model’s training without an attached excerpt. You can include a verse reference to ask about a specific text."));
      ui.cards.append(empty);
    }
    for (const source of sources) {
      const card = node("article", "source-card"); card.append(node("h3", "", source.reference));
      if (source.requested_reference && source.requested_reference !== source.reference) card.append(node("p", "source-reference-note", `Requested: ${source.requested_reference}. This edition: ${source.reference}.`));
      if (source.numbering) card.append(node("p", "source-numbering", source.numbering));
      const languages = { he: "Hebrew", heb: "Hebrew", hbo: "Hebrew", arc: "Aramaic", aramaic: "Aramaic", grc: "Greek", el: "Greek", greek: "Greek", hebrew: "Hebrew" };
      const language = source.language.toLowerCase();
      const meta = node("div", "source-meta"); meta.append(node("span", "", source.edition)); if (language) meta.append(node("span", "", languages[language] || source.language)); card.append(meta);
      const text = node("p", "source-text", source.text); text.dir = ["he", "heb", "hbo", "hebrew", "arc", "aramaic"].includes(language) ? "rtl" : "auto"; text.lang = language === "hbo" || language === "hebrew" ? "he" : language === "grc" || language === "greek" ? "el" : language === "aramaic" ? "arc" : language; card.append(text);
      if (source.editorial_status || source.editorial_notes.length) {
        const editorial = node("div", "source-editorial");
        const statuses = { supplement_only: "Supplemental text, separate from the main reading", main_with_doubtful_wording: "Main text includes doubtful wording", double_bracketed: "Double-bracketed addition", single_bracketed: "Single-bracketed doubtful wording", doubtful: "Doubtful wording", main: "Main text" };
        const readable = (value) => statuses[value] || value.replace(/_/g, " ");
        if (source.editorial_status) editorial.append(node("p", "", `Text status: ${readable(source.editorial_status)}.`));
        for (const note of source.editorial_notes) editorial.append(node("p", "", `${note.kind.replace(/_/g, " ")}: ${readable(note.status)}.`));
        card.append(editorial);
      }
      if (source.attribution) card.append(node("p", "source-attribution", source.attribution));
      try {
        const url = new URL(source.url);
        if (url.protocol === "https:" && !url.username && !url.password) {
          const link = node("a", "source-link", "View edition text ↗"); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link);
        }
      } catch { /* An invalid source URL remains noninteractive. */ }
      ui.cards.append(card);
    }
    if (!ui.drawer.open) ui.drawer.showModal();
  }

  function finishAnswer(job, payload) {
    const text = typeof payload.answer === "string" ? payload.answer : "";
    if (job.generation !== state.generation) return;
    const wasNearBottom = nearBottom();
    job.view.content.replaceChildren();
    const sources = safeSources(payload.sources);
    const sourceNotes = Array.isArray(payload.source_notes) ? payload.source_notes.filter((note) => typeof note === "string") : [];
    setSources(sources, sourceNotes);
    if (!text.trim()) {
      displayError(job, "No readable answer was returned this time. Your question hasn’t been sent again.");
      return;
    }
    renderAnswer(job.view.content, text);
    if (payload.complete === false) job.view.content.append(node("div", "incomplete-note", "This answer ended before it was finished. It is shown as returned, without continuing or sending your question again."));
    const footer = node("div", "message-footer");
    const passageButton = node("button", "", sources.length ? `View ${sources.length} supplied ${sources.length === 1 ? "passage" : "passages"}` : "Passages & source notes");
    passageButton.type = "button"; passageButton.setAttribute("aria-haspopup", "dialog"); passageButton.addEventListener("click", () => showSources(sources, sourceNotes)); footer.append(passageButton);
    const copy = node("button", "", "Copy answer"); copy.type = "button";
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text); copy.textContent = "Copied"; announce("Answer copied."); setTimeout(() => { copy.textContent = "Copy answer"; }, 2000); }
      catch { announce("Copy isn’t available here. You can select and copy the answer text."); }
    }); footer.append(copy); job.view.message.append(footer);
    state.history.push({ role: "user", content: job.question }, { role: "assistant", content: text });
    announce(payload.complete === false ? "A partial answer is available." : "The answer is ready.");
    if (wasNearBottom) scrollToConversation();
  }

  async function poll(job) {
    const until = Date.now() + 340000;
    while (state.job === job && Date.now() < until) {
      const result = await jsonRequest(`/api/chat/${encodeURIComponent(job.id)}`);
      if (result.status === "complete") return result;
      if (result.status === "error") return result;
      if (result.status !== "running") throw new Error("Unreadable request state");
      await pause(1500);
    }
    throw new Error("Polling paused");
  }

  async function waitForAnswer(job) {
    try {
      const result = await poll(job);
      if (state.job !== job) return;
      stopTimer(job);
      if (result.status === "error") displayError(job, "The model couldn’t finish this answer. Your question hasn’t been sent again.");
      else finishAnswer(job, result);
      state.job = null;
    } catch (error) {
      stopTimer(job);
      if (state.job !== job) return;
      if (error.status === 404 || error.status === 410) {
        displayError(job, "This answer is no longer available. You can edit your question to start a new request."); state.job = null;
      } else {
        job.paused = true;
        displayError(job, "The connection paused before we could retrieve the answer. You can check this same request; it won’t send the question again.", true);
      }
    } finally { refreshComposer(); }
  }

  async function resumeRequest(job = state.job) {
    if (!job || state.job !== job || !job.paused || !job.id) return;
    job.paused = false; showPending(job); refreshComposer(); await waitForAnswer(job);
  }

  async function submit(event) {
    event.preventDefault();
    const question = ui.question.value.trim();
    if (!question || !state.ready || state.job) return;
    const job = { generation: state.generation, question, id: null, startedAt: Date.now(), timer: null, paused: false, view: null };
    state.job = job;
    ui.welcome.hidden = true; ui.conversation.hidden = false; ui.main.classList.add("has-conversation");
    userMessage(question); job.view = assistantMessage(); showPending(job);
    ui.question.value = ""; resizeComposer(); refreshComposer(); scrollToConversation(); announce("Question sent. Waiting for the model’s answer.");
    const messages = state.history.concat({ role: "user", content: question });
    try {
      const accepted = await jsonRequest("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages }) });
      if (typeof accepted.request_id !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(accepted.request_id)) throw new Error("No request identifier");
      job.id = accepted.request_id;
    } catch (error) {
      const messages = {
        400: "That question couldn’t be sent. Try shortening it or starting a new conversation.",
        409: "Another request is still being answered. Please let it finish before asking again.",
        429: "This private preview has reached its current usage limit. Your question hasn’t been sent again.",
        503: "The model is not available right now. Your question hasn’t been sent again.",
      };
      displayError(job, messages[error.status] || "The connection closed before we could confirm this request. Your question hasn’t been sent again.");
      stopTimer(job); state.job = null; refreshComposer(); return;
    }
    await waitForAnswer(job);
  }

  function newChat() {
    state.generation += 1; state.history = []; setSources([]);
    ui.cards.replaceChildren(); ui.sourceNotes.replaceChildren();
    ui.messages.replaceChildren(); ui.conversation.hidden = true; ui.welcome.hidden = false; ui.main.classList.remove("has-conversation");
    ui.question.value = ""; resizeComposer(); if (ui.drawer.open) ui.drawer.close();
    // The server may already be working. Keep polling the original request to
    // release the single-request gate, but discard its result in this chat.
    refreshComposer(); announce("New conversation. Earlier messages have been cleared from this page.");
    window.scrollTo({ top: 0, behavior: "smooth" }); ui.question.focus({ preventScroll: true });
  }

  ui.form.addEventListener("submit", submit);
  ui.question.addEventListener("input", () => { resizeComposer(); refreshComposer(); });
  ui.question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); if (!ui.send.disabled) ui.form.requestSubmit(); }
  });
  for (const button of document.querySelectorAll("[data-question]")) button.addEventListener("click", () => {
    ui.question.value = button.dataset.question; resizeComposer(); refreshComposer(); ui.question.focus(); ui.question.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("new-chat").addEventListener("click", newChat);
  $("open-sources").addEventListener("click", () => showSources());
  $("close-sources").addEventListener("click", () => ui.drawer.close());
  ui.drawer.addEventListener("click", (event) => { if (event.target === ui.drawer && event.clientX < ui.drawer.getBoundingClientRect().left) ui.drawer.close(); });
  ui.checkConnection.addEventListener("click", checkConnection);
  ui.checkAnswer.addEventListener("click", () => resumeRequest());
  resizeComposer(); refreshComposer(); checkConnection();
})();
