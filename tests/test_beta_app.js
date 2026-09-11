"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SCRIPT = fs.readFileSync(
  path.resolve(__dirname, "../web/beta/app.js"),
  "utf8",
);
const MARKUP = fs.readFileSync(
  path.resolve(__dirname, "../web/beta/index.html"),
  "utf8",
);

const ELEMENT_IDS = [
  "login-view", "chat-view", "login-form", "login-button", "login-message",
  "chat-form", "question", "send-button", "request-state", "conversation",
  "welcome", "service-details", "logout-button", "new-chat-button",
  "sources-button", "sources-drawer", "close-sources", "source-cards",
  "source-notes", "invite-id", "invite-secret", "sign-in-button", "quota-hint",
  "auth-dialog", "auth-close-button", "auth-cancel-button", "email-form",
  "email-button", "auth-email", "code-form", "code-button", "code-email",
  "auth-token", "auth-message",
];

class FakeElement {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.listeners = new Map();
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.open = false;
    this.className = "";
    this.textContent = "";
    this.dir = "";
    this.lang = "";
    this.parentNode = null;
  }

  get firstChild() {
    return this.children[0] || null;
  }

  append(...children) {
    for (const child of children) {
      child.parentNode = this;
      this.children.push(child);
    }
  }

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    child.parentNode = null;
    return child;
  }

  addEventListener(type, callback) {
    const callbacks = this.listeners.get(type) || [];
    callbacks.push(callback);
    this.listeners.set(type, callbacks);
  }

  dispatch(type) {
    const event = { target: this, preventDefault() {} };
    return Promise.all((this.listeners.get(type) || []).map((callback) => callback(event)));
  }

  reset() {
    if (this.ownerDocument) {
      const controls = {
        "login-form": ["invite-id", "invite-secret"],
        "email-form": ["auth-email"],
        "code-form": ["auth-token"],
      }[this.id] || [];
      for (const id of controls) this.ownerDocument.querySelector(`#${id}`).value = "";
    }
  }

  focus() {}
  scrollIntoView() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
}

class FakeDocument {
  constructor() {
    this.elements = new Map();
    for (const id of ELEMENT_IDS) {
      const element = new FakeElement(id.includes("form") ? "form" : id.includes("dialog") ? "dialog" : "div", id);
      element.ownerDocument = this;
      this.elements.set(id, element);
    }
  }

  querySelector(selector) {
    assert.match(selector, /^#[a-z-]+$/);
    return this.elements.get(selector.slice(1));
  }

  createElement(tagName) {
    const element = new FakeElement(tagName);
    element.ownerDocument = this;
    return element;
  }
}

class FakeResponse {
  constructor(status, body) {
    this.status = status;
    this.ok = status >= 200 && status < 300;
    this.body = body;
  }

  async json() {
    return this.body;
  }
}

function response(status, body) {
  return Promise.resolve(new FakeResponse(status, body));
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

function allText(node) {
  return [node.textContent, ...node.children.flatMap(allText)].filter(Boolean).join("\n");
}

function descendants(node) {
  return node.children.flatMap((child) => [child, ...descendants(child)]);
}

function tags(node) {
  return descendants(node).map((child) => child.tagName);
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

async function boot(fetchImpl, storageSeed = {}) {
  const document = new FakeDocument();
  const storage = storageSeed instanceof Map ? storageSeed : new Map(Object.entries(storageSeed));
  const window = {
    setTimeout: (callback) => { callback(); return 1; },
    sessionStorage: {
      getItem: (key) => storage.has(key) ? storage.get(key) : null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    },
  };
  document.sessionStorage = window.sessionStorage;
  document.sessionStorageData = storage;
  const context = {
    document,
    window,
    fetch: fetchImpl,
    URL,
    console,
  };
  vm.runInNewContext(SCRIPT, context, { filename: "web/beta/app.js" });
  await flush();
  return document;
}

function publicAccess(emailLoginAvailable = true) {
  return { public_access: true, email_login_available: emailLoginAvailable };
}

function publicStatus(kind, remaining, resetAt = null) {
  return {
    public_model: "Meforash 0.1",
    source_count: 31152,
    conversation_storage: "not_stored",
    access: { kind, questions_remaining: remaining, daily_limit: 20, reset_at: resetAt },
  };
}

async function testLatePostCannotRestoreClearedConversation() {
  const chatPost = deferred();
  const calls = [];
  const document = await boot((url, options = {}) => {
    calls.push([url, options.method || "GET"]);
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return chatPost.promise;
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "A question that will be cleared";
  const submission = document.querySelector("#chat-form").dispatch("submit");
  await flush();
  await document.querySelector("#new-chat-button").dispatch("click");
  chatPost.resolve(new FakeResponse(202, { request_id: "late-post" }));
  await submission;
  assert.equal(document.querySelector("#conversation").children.length, 0);
  assert.equal(document.querySelector("#question").value, "");
  assert.equal(document.querySelector("#request-state").textContent, "Ready");
  assert.deepEqual(calls, [["/api/access", "GET"], ["/api/status", "GET"], ["/api/chat", "POST"]]);
}

async function testLatePollCannotChangeSignedOutView() {
  const chatPoll = deferred();
  const logoutPost = deferred();
  let pollCalls = 0;
  const document = await boot((url, options = {}) => {
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return response(202, { request_id: "late-poll" });
    if (url === "/api/chat/late-poll") {
      pollCalls += 1;
      return pollCalls === 1
        ? response(200, { status: "running", revision: 1, answer: "Late partial", complete: false })
        : chatPoll.promise;
    }
    if (url === "/api/logout" && options.method === "POST") return logoutPost.promise;
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "A question already submitted";
  const submission = document.querySelector("#chat-form").dispatch("submit");
  await flush();
  assert.equal(document.querySelector("#conversation").children.length, 2);
  const signout = document.querySelector("#logout-button").dispatch("click");
  assert.equal(document.querySelector("#login-view").hidden, false);
  assert.equal(document.querySelector("#conversation").children.length, 0);
  assert.equal(document.querySelector("#login-button").disabled, true);
  logoutPost.resolve(new FakeResponse(200, {}));
  await signout;
  assert.equal(document.querySelector("#login-button").disabled, false);
  chatPoll.resolve(new FakeResponse(200, {
    status: "complete",
    answer: "A response that arrived after sign-out.",
    complete: true,
    sources: [{ reference: "Genesis 1:1", text: "בְּרֵאשִׁית", language: "hbo" }],
    source_notes: ["A late source note."],
  }));
  await submission;
  assert.equal(document.querySelector("#conversation").children.length, 0);
  assert.equal(document.querySelector("#source-cards").children.length, 0);
  assert.equal(document.querySelector("#sources-button").hidden, true);
  assert.equal(document.querySelector("#login-message").textContent,
    "Signed out. Conversation history was cleared from this page.");
}

async function testSourceCardsPreserveTextLayers() {
  const sources = [
    {
      reference: "Exodus 3:14",
      requested_reference: "English Exodus 3:14",
      numbering: "Mapped to the selected Hebrew edition",
      edition: "OSHB fixture",
      language: "hbo",
      text: "אֶהְיֶה",
      editorial_status: "main_with_doubtful_wording",
      editorial_notes: [{ kind: "addition", status: "double_bracketed" }],
      attribution: "Hebrew fixture attribution",
    },
    { reference: "Daniel 2:4", edition: "OSHB fixture", language: "arc", text: "אֲרָמִית" },
    { reference: "John 1:1", edition: "SBLGNT fixture", language: "grc", text: "Ἐν ἀρχῇ" },
  ];
  const document = await boot((url) => {
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return response(202, { request_id: "source-result" });
    if (url === "/api/chat/source-result") return response(200, {
      status: "complete", answer: "A source-aware answer.", complete: true,
      sources, source_notes: ["Fixture source limit."],
    });
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "Compare the supplied passages";
  await document.querySelector("#chat-form").dispatch("submit");
  const cards = document.querySelector("#source-cards").children;
  assert.equal(cards.length, 3);
  assert.match(allText(cards[0]), /Requested: English Exodus 3:14\. This edition: Exodus 3:14\./);
  assert.match(allText(cards[0]), /Mapped to the selected Hebrew edition/);
  assert.match(allText(cards[0]), /Text status: Main text includes doubtful wording\./);
  assert.match(allText(cards[0]), /addition: Double-bracketed addition\./);
  assert.match(allText(cards[0]), /Hebrew/);
  assert.match(allText(cards[1]), /Aramaic/);
  assert.match(allText(cards[2]), /Greek/);
  const sourceTexts = cards.map((card) => descendants(card).find((node) => node.className === "source-text"));
  assert.deepEqual(sourceTexts.map((node) => [node.dir, node.lang]),
    [["rtl", "he"], ["rtl", "arc"], ["auto", "el"]]);
  assert.equal(document.querySelector("#source-notes").children[0].textContent, "Fixture source limit.");
}

async function testAnswerFormattingUsesOnlySafeDomNodes() {
  const answer = "## Main point\n\n**Grace** and *peace* frame the answer.\n\n- First reading\n- Second `term`\n\n[Unsafe link](javascript:alert(1)) <img src=x onerror=alert(2)>\n\n### \n- \n1. ";
  const document = await boot((url) => {
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return response(202, { request_id: "formatted" });
    if (url === "/api/chat/formatted") return response(200, {
      status: "complete", answer, complete: true, sources: [], source_notes: [],
    });
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "Format this safely";
  await document.querySelector("#chat-form").dispatch("submit");
  const assistant = document.querySelector("#conversation").children[1];
  assert.deepEqual(tags(assistant), ["P", "DIV", "H3", "SPAN", "P", "STRONG", "SPAN", "EM", "SPAN", "UL", "LI", "SPAN", "LI", "SPAN", "CODE", "P", "SPAN", "P", "SPAN", "P", "SPAN", "P", "SPAN"]);
  assert.match(allText(assistant), /\[Unsafe link\]\(javascript:alert\(1\)\)/);
  assert.match(allText(assistant), /<img src=x onerror=alert\(2\)>/);
  assert.ok(!tags(assistant).includes("A"));
  assert.ok(!tags(assistant).includes("IMG"));
  assert.match(allText(assistant), /###/);
  assert.match(allText(assistant), /1\./);
}

async function testProgressReplacesPlainNodeAndTerminalRendersOnce() {
  const terminal = deferred();
  let polls = 0;
  const document = await boot((url) => {
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return response(202, { request_id: "progressive" });
    if (url === "/api/chat/progressive") {
      polls += 1;
      if (polls === 1) {
        return response(200, { status: "running", revision: 1,
          answer: "Draft **bold", complete: false });
      }
      if (polls === 2) {
        return response(200, { status: "running", revision: 1,
          answer: "Duplicate must be ignored", complete: false });
      }
      if (polls === 3) {
        return response(200, { status: "running", revision: 0,
          answer: "Older must be ignored", complete: false });
      }
      if (polls === 4) {
        return response(200, { status: "running", revision: 2,
          answer: "Draft **bold** complete", complete: false });
      }
      return terminal.promise;
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  document.querySelector("#question").value = "Show progress";
  const submission = document.querySelector("#chat-form").dispatch("submit");
  await flush();
  const inProgress = document.querySelector("#conversation").children;
  assert.equal(inProgress.length, 2);
  assert.match(inProgress[1].className, /message-progress/);
  assert.equal(inProgress[1].children[1].textContent, "Draft **bold** complete");
  assert.equal(tags(inProgress[1]).includes("STRONG"), false);

  terminal.resolve(new FakeResponse(200, {
    status: "complete", revision: 3, answer: "Final **bold** answer.",
    complete: true, sources: [], source_notes: [], warnings: [],
  }));
  await submission;
  const completed = document.querySelector("#conversation").children;
  assert.equal(completed.length, 2);
  assert.doesNotMatch(completed[1].className, /message-progress/);
  assert.equal(tags(completed[1]).filter((tag) => tag === "STRONG").length, 1);
  assert.equal(allText(completed[1]).match(/Final/g).length, 1);
}

async function testPartialErrorIsVisibleButExcludedFromLaterContext() {
  let chatCalls = 0;
  let partialPolls = 0;
  let statusCalls = 0;
  let laterPayload = null;
  const document = await boot((url, options = {}) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") {
      statusCalls += 1;
      return response(200, publicStatus("account", statusCalls === 1 ? 19 : 18));
    }
    if (url === "/api/chat") {
      chatCalls += 1;
      if (chatCalls === 1) return response(202, { request_id: "partial-error" });
      laterPayload = JSON.parse(options.body);
      return response(202, { request_id: "later-answer" });
    }
    if (url === "/api/chat/partial-error") {
      partialPolls += 1;
      return partialPolls === 1
        ? response(200, { status: "running", revision: 1,
          answer: "Safe partial", complete: false })
        : response(200, { status: "error", revision: 1,
          partial_answer: "Safe partial", complete: false,
          error: { code: "generation_unavailable", message: "Generation stopped." } });
    }
    if (url === "/api/chat/later-answer") return response(200, {
      status: "complete", revision: 1, answer: "Later complete answer.",
      complete: true, sources: [], source_notes: [], warnings: [],
    });
    throw new Error(`Unexpected fetch: ${url}`);
  });

  document.querySelector("#question").value = "First uncertain question";
  await document.querySelector("#chat-form").dispatch("submit");
  assert.match(allText(document.querySelector("#conversation")), /Safe partial/);
  assert.match(allText(document.querySelector("#conversation")),
    /incomplete and will not be included in later questions/);
  assert.match(document.querySelector("#quota-hint").textContent,
    /18 questions remaining today/);

  document.querySelector("#question").value = "Later question";
  await document.querySelector("#chat-form").dispatch("submit");
  assert.ok(laterPayload);
  assert.equal(laterPayload.messages.some((message) => message.content === "Safe partial"), false);
  assert.equal(laterPayload.messages.some((message) => /incomplete/.test(message.content)), false);
}

async function testNetworkFailureAfterProgressLabelsPartialAndDoesNotRetry() {
  let polls = 0;
  const document = await boot((url) => {
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return response(202, { request_id: "network-partial" });
    if (url === "/api/chat/network-partial") {
      polls += 1;
      if (polls === 1) return response(200, {
        status: "running", revision: 1, answer: "Visible before disconnect",
        complete: false,
      });
      return Promise.reject(new Error("private network detail"));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  document.querySelector("#question").value = "Disconnect after progress";
  await document.querySelector("#chat-form").dispatch("submit");
  const text = allText(document.querySelector("#conversation"));
  assert.match(text, /Visible before disconnect/);
  assert.match(text, /partial answer above is incomplete/);
  assert.doesNotMatch(text, /private network detail/);
  assert.equal(polls, 2);
}

function testReaderFacingCopyKeepsLimitsVisibleAndOperationsQuiet() {
  assert.match(MARKUP, /Meforash/);
  assert.match(MARKUP, /Original-language Bible exploration/);
  assert.match(MARKUP, /is not used(?: by Meforash)? for training/);
  assert.match(MARKUP, /not the original manuscripts/);
  assert.doesNotMatch(MARKUP, /Thinking Machines|starter prompt|provider/i);
  assert.match(MARKUP, /<details class="about-panel/);
  assert.match(MARKUP, /pattern="\[0-9\]\{6\}"/);
  assert.match(MARKUP, /Saved history is not available yet/);
  assert.match(MARKUP, /temporary session storage for up to ten minutes/);
  assert.doesNotMatch(MARKUP, /not written to disk/);
}

async function testGuestLimitAndCodeSignInPreservePageState() {
  let statusCalls = 0;
  let verifyCalls = 0;
  const document = await boot((url, options = {}) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") {
      statusCalls += 1;
      return statusCalls === 1
        ? response(401, { error: { code: "unauthorized" } })
        : response(200, publicStatus("guest", 0));
    }
    if (url === "/api/guest") return response(200, publicStatus("guest", 3));
    if (url === "/api/chat" && JSON.parse(options.body).messages.at(-1).content === "First question") {
      return response(202, { request_id: "guest-answer" });
    }
    if (url === "/api/chat/guest-answer") return response(200, {
      status: "complete", answer: "First answer", complete: true,
      sources: [{ reference: "Genesis 1:1", text: "בְּרֵאשִׁית", language: "hbo" }],
      source_notes: ["Selected edition."],
    });
    if (url === "/api/chat") return response(403, {
      error: { code: "guest_limit_reached", message: "Sign in to keep asking questions." },
    });
    if (url === "/api/auth/start") return response(200, { status: "code_sent" });
    if (url === "/api/auth/verify") {
      verifyCalls += 1;
      return verifyCalls === 1
        ? response(401, { error: { code: "invalid_code", message: "That code was not accepted." } })
        : response(200, publicStatus("account", 20, "2026-09-12T05:00:00Z"));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  assert.equal(document.querySelector("#chat-view").hidden, false);
  assert.equal(document.querySelector("#sign-in-button").hidden, false);
  assert.match(document.querySelector("#quota-hint").textContent, /3 of 3 free guest questions/);

  document.querySelector("#question").value = "First question";
  await document.querySelector("#chat-form").dispatch("submit");
  assert.equal(document.querySelector("#conversation").children.length, 2);
  assert.match(document.querySelector("#quota-hint").textContent, /0 of 3/);

  document.querySelector("#question").value = "Unsent draft stays here";
  await document.querySelector("#chat-form").dispatch("submit");
  assert.equal(document.querySelector("#auth-dialog").open, true);
  assert.equal(document.querySelector("#conversation").children.length, 2);
  assert.equal(document.querySelector("#question").value, "Unsent draft stays here");
  assert.ok(document.sessionStorage.getItem("meforash.auth-handoff.v1"));

  document.querySelector("#auth-email").value = "reader@example.test";
  await document.querySelector("#email-form").dispatch("submit");
  assert.equal(document.querySelector("#code-form").hidden, false);
  document.querySelector("#auth-token").value = "12345678";
  await document.querySelector("#code-form").dispatch("submit");
  assert.equal(document.querySelector("#auth-dialog").open, true);
  assert.equal(document.querySelector("#auth-message").textContent, "That code was not accepted.");
  assert.equal(document.querySelector("#conversation").children.length, 2);

  document.querySelector("#auth-token").value = "87654321";
  await document.querySelector("#code-form").dispatch("submit");
  assert.equal(document.querySelector("#auth-dialog").open, false);
  assert.equal(document.querySelector("#conversation").children.length, 2);
  assert.equal(document.querySelector("#source-cards").children.length, 1);
  assert.equal(document.querySelector("#question").value, "Unsent draft stays here");
  assert.equal(document.querySelector("#sign-in-button").hidden, true);
  assert.equal(document.querySelector("#logout-button").hidden, false);
  assert.equal(document.sessionStorage.getItem("meforash.auth-handoff.v1"), null);
}

async function testCancelSignInKeepsDraftAndClearsHandoff() {
  const document = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("guest", 2));
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "Draft before cancel";
  await document.querySelector("#sign-in-button").dispatch("click");
  assert.ok(document.sessionStorage.getItem("meforash.auth-handoff.v1"));
  await document.querySelector("#auth-cancel-button").dispatch("click");
  assert.equal(document.querySelector("#auth-dialog").open, false);
  assert.equal(document.querySelector("#question").value, "Draft before cancel");
  assert.equal(document.sessionStorage.getItem("meforash.auth-handoff.v1"), null);
}

async function testGuestBootstrapFailureKeepsPublicEmailSignInAvailable() {
  const calls = [];
  const handoff = JSON.stringify({
    version: 1,
    expires_at: Date.now() + 60000,
    messages: [
      { role: "user", content: "Question before sign-in" },
      { role: "assistant", content: "Answer before sign-in" },
    ],
    draft: "Saved draft must not submit itself",
    sources: [],
    source_notes: [],
  });
  const document = await boot((url, options = {}) => {
    calls.push([url, options.method || "GET"]);
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") {
      return response(401, { error: { code: "unauthorized" } });
    }
    if (url === "/api/guest") {
      return response(429, {
        error: { code: "rate_limited", message: "Please wait before trying again." },
      });
    }
    if (url === "/api/auth/start") return response(200, { status: "code_sent" });
    if (url === "/api/auth/verify") return response(200, publicStatus("account", 20));
    throw new Error(`Unexpected fetch: ${url}`);
  }, { "meforash.auth-handoff.v1": handoff });

  assert.equal(document.querySelector("#login-view").hidden, true);
  assert.equal(document.querySelector("#chat-view").hidden, false);
  assert.equal(document.querySelector("#sign-in-button").hidden, false);
  assert.equal(document.querySelector("#new-chat-button").hidden, true);
  assert.equal(document.querySelector("#question").disabled, true);
  assert.equal(document.querySelector("#send-button").disabled, true);
  assert.equal(document.querySelector("#request-state").textContent,
    "Please wait before trying again.");
  assert.match(document.querySelector("#quota-hint").textContent,
    /Guest access is temporarily unavailable.*Sign in with email/);
  assert.equal(document.querySelector("#conversation").children.length, 2);
  assert.equal(document.querySelector("#question").value,
    "Saved draft must not submit itself");
  assert.ok(document.sessionStorage.getItem("meforash.auth-handoff.v1"));
  assert.equal(calls.some(([url]) => url === "/api/chat"), false);

  await document.querySelector("#sign-in-button").dispatch("click");
  assert.equal(document.querySelector("#auth-dialog").open, true);
  await document.querySelector("#auth-cancel-button").dispatch("click");
  assert.equal(document.querySelector("#auth-dialog").open, false);
  assert.equal(document.querySelector("#question").disabled, true);
  assert.equal(document.querySelector("#question").value,
    "Saved draft must not submit itself");

  await document.querySelector("#sign-in-button").dispatch("click");
  document.querySelector("#auth-email").value = "reader@example.test";
  await document.querySelector("#email-form").dispatch("submit");
  document.querySelector("#auth-token").value = "12345678";
  await document.querySelector("#code-form").dispatch("submit");
  assert.equal(document.querySelector("#auth-dialog").open, false);
  assert.equal(document.querySelector("#question").disabled, false);
  assert.equal(document.querySelector("#conversation").children.length, 2);
  assert.equal(document.querySelector("#question").value,
    "Saved draft must not submit itself");
  assert.equal(document.querySelector("#sign-in-button").hidden, true);
  assert.equal(document.querySelector("#logout-button").hidden, false);
  assert.equal(calls.some(([url]) => url === "/api/chat"), false);
}

async function testGuestRecoveryFailureNeverFallsBackToInvitationLogin() {
  let chatCalls = 0;
  const document = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("guest", 2));
    if (url === "/api/chat") {
      chatCalls += 1;
      return response(401, { error: { code: "unauthorized" } });
    }
    if (url === "/api/guest") {
      return response(429, {
        error: { code: "rate_limited", message: "Please wait before trying again." },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  document.querySelector("#question").value = "Keep this draft after expiry";
  await document.querySelector("#chat-form").dispatch("submit");
  assert.equal(document.querySelector("#login-view").hidden, true);
  assert.equal(document.querySelector("#chat-view").hidden, false);
  assert.equal(document.querySelector("#sign-in-button").hidden, false);
  assert.equal(document.querySelector("#question").disabled, true);
  assert.equal(document.querySelector("#question").value,
    "Keep this draft after expiry");
  assert.equal(chatCalls, 1);
}

async function testAccountSignOutInvalidatesLatePollAndReturnsToGuest() {
  const latePoll = deferred();
  const document = await boot((url, options = {}) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("account", 19));
    if (url === "/api/chat") return response(202, { request_id: "old-account" });
    if (url === "/api/chat/old-account") return latePoll.promise;
    if (url === "/api/logout" && options.method === "POST") return response(200, {});
    if (url === "/api/guest" && options.method === "POST") return response(200, publicStatus("guest", 2));
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "Account request";
  const submission = document.querySelector("#chat-form").dispatch("submit");
  await flush();
  assert.equal(document.querySelector("#conversation").children.length, 1);
  await document.querySelector("#logout-button").dispatch("click");
  assert.equal(document.querySelector("#conversation").children.length, 0);
  assert.equal(document.querySelector("#question").value, "");
  assert.equal(document.querySelector("#sign-in-button").hidden, false);
  assert.match(document.querySelector("#quota-hint").textContent, /2 of 3/);
  latePoll.resolve(new FakeResponse(200, {
    status: "complete", answer: "Old account answer", complete: true,
    sources: [], source_notes: [],
  }));
  await submission;
  assert.equal(document.querySelector("#conversation").children.length, 0);
}

async function testSuccessfulAccountLogoutWithUnavailableGuestUsesEmailState() {
  const calls = [];
  const document = await boot((url, options = {}) => {
    calls.push([url, options.method || "GET"]);
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("account", 19));
    if (url === "/api/logout" && options.method === "POST") return response(200, {});
    if (url === "/api/guest" && options.method === "POST") {
      return response(429, {
        error: { code: "rate_limited", message: "Please wait before trying again." },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  await document.querySelector("#logout-button").dispatch("click");
  assert.equal(document.querySelector("#login-view").hidden, true);
  assert.equal(document.querySelector("#chat-view").hidden, false);
  assert.equal(document.querySelector("#sign-in-button").hidden, false);
  assert.equal(document.querySelector("#logout-button").hidden, true);
  assert.equal(document.querySelector("#new-chat-button").hidden, true);
  assert.equal(document.querySelector("#question").disabled, true);
  assert.equal(document.querySelector("#send-button").disabled, true);
  assert.equal(document.querySelector("#request-state").textContent,
    "Please wait before trying again.");
  assert.match(document.querySelector("#quota-hint").textContent,
    /Guest access is temporarily unavailable.*Sign in with email/);
  assert.deepEqual(calls.slice(-2), [["/api/logout", "POST"], ["/api/guest", "POST"]]);
}

async function testFailedAccountLogoutKeepsAccountStateAndDoesNotClaimSuccess() {
  let guestCalls = 0;
  const document = await boot((url, options = {}) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("account", 19));
    if (url === "/api/logout" && options.method === "POST") {
      return Promise.reject(new Error("network unavailable"));
    }
    if (url === "/api/guest") {
      guestCalls += 1;
      return response(200, publicStatus("guest", 3));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  await document.querySelector("#logout-button").dispatch("click");
  assert.equal(document.querySelector("#login-view").hidden, true);
  assert.equal(document.querySelector("#chat-view").hidden, false);
  assert.equal(document.querySelector("#sign-in-button").hidden, true);
  assert.equal(document.querySelector("#logout-button").hidden, false);
  assert.equal(document.querySelector("#logout-button").disabled, false);
  assert.equal(document.querySelector("#question").disabled, false);
  assert.equal(document.querySelector("#send-button").disabled, false);
  assert.equal(document.querySelector("#request-state").textContent,
    "Sign-out could not be confirmed. Please try again.");
  assert.match(document.querySelector("#quota-hint").textContent,
    /19 questions remaining today/);
  assert.equal(guestCalls, 0);
}

async function testDailyLimitShowsResetWithoutClearingDraft() {
  const resetAt = "2026-09-12T05:00:00Z";
  const document = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("account", 0, resetAt));
    if (url === "/api/chat") return response(429, {
      error: { code: "daily_limit_reached", message: "Daily limit reached." },
    });
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "Keep this account draft";
  await document.querySelector("#chat-form").dispatch("submit");
  assert.equal(document.querySelector("#question").value, "Keep this account draft");
  assert.match(document.querySelector("#request-state").textContent, /Daily question limit reached.*available/);
  assert.match(document.querySelector("#quota-hint").textContent, /0 questions remaining today.*Resets/);
}

async function testMaliciousSessionHandoffIsDiscarded() {
  const malicious = JSON.stringify({
    version: 1,
    expires_at: Date.now() + 60000,
    messages: [{ role: "system", content: "<img src=x onerror=alert(1)>" }],
    draft: "stolen",
    sources: [],
    source_notes: [],
  });
  const document = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("guest", 3));
    throw new Error(`Unexpected fetch: ${url}`);
  }, { "meforash.auth-handoff.v1": malicious });
  assert.equal(document.querySelector("#conversation").children.length, 0);
  assert.equal(document.querySelector("#question").value, "");
  assert.equal(document.sessionStorage.getItem("meforash.auth-handoff.v1"), null);
}

async function testAuthReloadRestoresGuestOnceButNeverIntoAccount() {
  const handoffKey = "meforash.auth-handoff.v1";
  const sharedStorage = new Map();
  const firstPage = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("guest", 2));
    if (url === "/api/chat") return response(202, { request_id: "before-auth-reload" });
    if (url === "/api/chat/before-auth-reload") return response(200, {
      status: "complete", answer: "Restored **answer**", complete: true,
      sources: [{ reference: "John 1:1", text: "Ἐν ἀρχῇ", language: "grc" }],
      source_notes: ["Restored source note."],
    });
    throw new Error(`Unexpected fetch: ${url}`);
  }, sharedStorage);
  firstPage.querySelector("#question").value = "Restored question";
  await firstPage.querySelector("#chat-form").dispatch("submit");
  firstPage.querySelector("#question").value = "Restored unsent draft";
  await firstPage.querySelector("#sign-in-button").dispatch("click");
  const recoveryValue = sharedStorage.get(handoffKey);
  assert.ok(recoveryValue);
  const recovery = JSON.parse(recoveryValue);
  assert.ok(recovery.expires_at <= Date.now() + 10 * 60 * 1000);

  const reloadedGuest = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("guest", 2));
    throw new Error(`Unexpected fetch: ${url}`);
  }, sharedStorage);
  assert.equal(reloadedGuest.querySelector("#conversation").children.length, 2);
  const restoredText = allText(reloadedGuest.querySelector("#conversation"));
  assert.match(restoredText, /Restored/);
  assert.match(restoredText, /answer/);
  assert.equal(reloadedGuest.querySelector("#question").value, "Restored unsent draft");
  assert.equal(reloadedGuest.querySelector("#source-cards").children.length, 1);
  assert.equal(reloadedGuest.querySelector("#source-notes").children[0].textContent, "Restored source note.");
  assert.equal(sharedStorage.has(handoffKey), false);

  sharedStorage.set(handoffKey, recoveryValue);
  const laterAccount = await boot((url) => {
    if (url === "/api/access") return response(200, publicAccess());
    if (url === "/api/status") return response(200, publicStatus("account", 20));
    throw new Error(`Unexpected fetch: ${url}`);
  }, sharedStorage);
  assert.equal(laterAccount.querySelector("#conversation").children.length, 0);
  assert.equal(laterAccount.querySelector("#question").value, "");
  assert.equal(laterAccount.querySelector("#source-cards").children.length, 0);
  assert.equal(sharedStorage.has(handoffKey), false);
}

(async () => {
  testReaderFacingCopyKeepsLimitsVisibleAndOperationsQuiet();
  await testLatePostCannotRestoreClearedConversation();
  await testLatePollCannotChangeSignedOutView();
  await testSourceCardsPreserveTextLayers();
  await testAnswerFormattingUsesOnlySafeDomNodes();
  await testProgressReplacesPlainNodeAndTerminalRendersOnce();
  await testPartialErrorIsVisibleButExcludedFromLaterContext();
  await testNetworkFailureAfterProgressLabelsPartialAndDoesNotRetry();
  await testGuestLimitAndCodeSignInPreservePageState();
  await testCancelSignInKeepsDraftAndClearsHandoff();
  await testGuestBootstrapFailureKeepsPublicEmailSignInAvailable();
  await testGuestRecoveryFailureNeverFallsBackToInvitationLogin();
  await testAccountSignOutInvalidatesLatePollAndReturnsToGuest();
  await testSuccessfulAccountLogoutWithUnavailableGuestUsesEmailState();
  await testFailedAccountLogoutKeepsAccountStateAndDoesNotClaimSuccess();
  await testDailyLimitShowsResetWithoutClearingDraft();
  await testMaliciousSessionHandoffIsDiscarded();
  await testAuthReloadRestoresGuestOnceButNeverIntoAccount();
  process.stdout.write("3 beta browser regression scenarios passed; 3 progressive answer scenarios passed; 10 public access scenarios passed; 3 presentation safety scenarios passed\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
