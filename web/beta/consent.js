"use strict";

(() => {
  const VERSION = "2026-09-11.1";
  const form = document.querySelector("#chat-form");
  const message = document.querySelector("#chat-consent-message");
  let pending = false;
  let replay = false;

  async function api(path, body) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...(body ? { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) throw new Error("consent_unavailable");
    return response.json();
  }

  async function recordAcceptanceForCurrentIdentity() {
    try {
      const status = await api("/api/status");
      if (status.access?.terms_accepted === true
          && status.access?.terms_version === VERSION) return;
    } catch (_) {
      // The action-bound acceptance request below provides the useful error.
    }
    const status = await api("/api/accept-terms", {
      terms_version: VERSION,
      adult: true,
    });
    if (status.access?.terms_accepted !== true
        || status.access?.terms_version !== VERSION) {
      throw new Error("consent_unavailable");
    }
  }

  form.addEventListener("submit", (event) => {
    if (replay) {
      replay = false;
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    if (pending) return;
    pending = true;
    message.textContent = "";
    recordAcceptanceForCurrentIdentity().then(() => {
      replay = true;
      form.requestSubmit();
    }).catch(() => {
      message.textContent = "We could not record your agreement. Please try again, or refresh and sign in. Your question has not been sent.";
    }).finally(() => {
      pending = false;
    });
  }, true);
})();
