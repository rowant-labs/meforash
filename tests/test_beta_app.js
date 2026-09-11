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
  "source-notes", "invite-id", "invite-secret",
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
    // The beta form contains only these two controls.
    if (this.ownerDocument) {
      this.ownerDocument.querySelector("#invite-id").value = "";
      this.ownerDocument.querySelector("#invite-secret").value = "";
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
      const element = new FakeElement(id.includes("form") ? "form" : "div", id);
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

async function boot(fetchImpl) {
  const document = new FakeDocument();
  const window = { setTimeout: (callback) => { callback(); return 1; } };
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
  assert.deepEqual(calls, [["/api/status", "GET"], ["/api/chat", "POST"]]);
}

async function testLatePollCannotChangeSignedOutView() {
  const chatPoll = deferred();
  const logoutPost = deferred();
  const document = await boot((url, options = {}) => {
    if (url === "/api/status") return response(200, { model: "Inkling B" });
    if (url === "/api/chat") return response(202, { request_id: "late-poll" });
    if (url === "/api/chat/late-poll") return chatPoll.promise;
    if (url === "/api/logout" && options.method === "POST") return logoutPost.promise;
    throw new Error(`Unexpected fetch: ${url}`);
  });
  document.querySelector("#question").value = "A question already submitted";
  const submission = document.querySelector("#chat-form").dispatch("submit");
  await flush();
  assert.equal(document.querySelector("#conversation").children.length, 1);
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

function testReaderFacingCopyKeepsLimitsVisibleAndOperationsQuiet() {
  assert.match(MARKUP, /Meforash/);
  assert.match(MARKUP, /Original-language Bible exploration/);
  assert.match(MARKUP, /is not used(?: by Meforash)? for training/);
  assert.match(MARKUP, /not the original manuscripts/);
  assert.doesNotMatch(MARKUP, /Thinking Machines|starter prompt|provider/i);
  assert.match(MARKUP, /<details class="about-panel/);
}

(async () => {
  testReaderFacingCopyKeepsLimitsVisibleAndOperationsQuiet();
  await testLatePostCannotRestoreClearedConversation();
  await testLatePollCannotChangeSignedOutView();
  await testSourceCardsPreserveTextLayers();
  await testAnswerFormattingUsesOnlySafeDomNodes();
  process.stdout.write("3 beta browser regression scenarios passed; 2 presentation safety scenarios passed\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
