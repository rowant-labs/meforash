"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("web/beta/consent.js", "utf8");
const markup = fs.readFileSync("web/beta/index.html", "utf8");

function event() {
  return { preventDefault() {}, stopImmediatePropagation() {} };
}

function setup({ accepted = false, failAcceptance = false } = {}) {
  const nodes = new Map();
  const calls = [];
  function node(id) {
    if (!nodes.has(id)) {
      nodes.set(id, {
        value: "",
        textContent: "",
        handlers: {},
        replays: 0,
        addEventListener(type, fn) { this.handlers[type] = fn; },
        requestSubmit() { this.replays += 1; this.handlers.submit(event()); },
      });
    }
    return nodes.get(id);
  }
  const fetch = async (path, options) => {
    calls.push({ path, options });
    if (path === "/api/status") {
      return { ok: true, json: async () => ({ access: {
        terms_accepted: accepted,
        terms_version: "2026-09-11.1",
      } }) };
    }
    if (path === "/api/accept-terms") {
      return { ok: !failAcceptance, json: async () => ({ access: {
        terms_accepted: true,
        terms_version: "2026-09-11.1",
      } }) };
    }
    throw new Error(`unexpected path: ${path}`);
  };
  vm.runInNewContext(source, {
    document: { querySelector: node },
    fetch,
    Promise,
    Error,
  });
  return { node, calls };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
  let page = setup();
  assert.deepEqual(page.calls, []);
  assert.doesNotMatch(markup, /consent-dialog|consent-check|Agree and continue/);
  assert.match(markup, /By selecting <strong>Send question<\/strong>/);
  assert.match(markup, /By selecting <strong>Send a sign-in code<\/strong>/);
  assert.match(markup, /By selecting <strong>Verify code<\/strong>/);
  assert.equal((markup.match(/Terms of Service<\/a>/g) || []).length, 3);
  assert.equal((markup.match(/Privacy Policy<\/a>/g) || []).length, 3);

  page.node("#chat-form").value = "Unchanged draft";
  page.node("#chat-form").handlers.submit(event());
  await flush();
  assert.equal(page.node("#chat-form").replays, 1);
  assert.equal(page.node("#chat-form").value, "Unchanged draft");
  assert.deepEqual(page.calls.map((call) => call.path),
    ["/api/status", "/api/accept-terms"]);
  assert.deepEqual(JSON.parse(page.calls[1].options.body), {
    terms_version: "2026-09-11.1",
    adult: true,
  });

  page = setup({ accepted: true });
  page.node("#chat-form").handlers.submit(event());
  await flush();
  assert.equal(page.node("#chat-form").replays, 1);
  assert.deepEqual(page.calls.map((call) => call.path), ["/api/status"]);

  page = setup({ failAcceptance: true });
  page.node("#chat-form").handlers.submit(event());
  await flush();
  assert.equal(page.node("#chat-form").replays, 0);
  assert.match(page.node("#chat-consent-message").textContent,
    /question has not been sent/);

  process.stdout.write("4 inline action-consent scenarios passed\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
