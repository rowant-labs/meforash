"use strict";

(() => {
  const VERSION = "2026-09-11";
  const dialog = document.querySelector("#consent-dialog");
  const consentForm = document.querySelector("#consent-form");
  const check = document.querySelector("#consent-check");
  const error = document.querySelector("#consent-error");
  const cancel = document.querySelector("#consent-cancel");
  const replay = new WeakSet();
  const pending = new WeakSet();
  let resolveChoice = null;
  let record = false;
  let saving = false;

  async function api(path, body) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...(body ? { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) throw new Error("consent_unavailable");
    return response.json();
  }

  function finish(accepted) {
    dialog.close();
    const done = resolveChoice;
    resolveChoice = null;
    if (done) done(accepted);
  }

  async function ensure(kind) {
    if (kind === "chat") {
      try {
        const status = await api("/api/status");
        if (status.access?.terms_accepted === true && status.access?.terms_version === VERSION) return true;
      } catch (_) {
        // The acceptance endpoint will show an actionable error without submitting a question.
      }
    }
    if (resolveChoice) return false;
    record = kind === "chat";
    check.checked = false;
    error.textContent = "";
    dialog.showModal();
    check.focus();
    return new Promise((resolve) => { resolveChoice = resolve; });
  }

  consentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!check.checked || saving) return;
    saving = true;
    try {
      if (record) await api("/api/accept-terms", {terms_version: VERSION, adult: true});
      finish(true);
    } catch (_) {
      error.textContent = "We could not record your agreement. Please try again, or refresh and sign in. Your question has not been sent.";
    } finally {
      saving = false;
    }
  });
  cancel.addEventListener("click", () => { if (!saving) finish(false); });
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); if (!saving) finish(false); });

  for (const [selector, kind] of [["#chat-form", "chat"], ["#email-form", "email"]]) {
    const form = document.querySelector(selector);
    form.addEventListener("submit", (event) => {
      if (replay.has(form)) { replay.delete(form); return; }
      event.preventDefault();
      event.stopImmediatePropagation();
      if (pending.has(form)) return;
      pending.add(form);
      ensure(kind).then((accepted) => {
        if (accepted) { replay.add(form); form.requestSubmit(); }
      }).finally(() => pending.delete(form));
    }, true);
  }
})();
