"use strict";
(() => {
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/assets/auth.css";
  document.head.appendChild(style);

  const ACCOUNT_KEY = "tendergraph.productAccountId.v1";
  const PROFILE_KEY = "tendergraph.companyProfile.v1";
  const SAVED_KEY = "tendergraph.savedOpportunities.v1";
  const IGNORED_KEY = "tendergraph.ignoredOpportunities.v1";
  const DIRTY_KEY = "tendergraph.persistenceDirty.v1";

  const request = async (path, options = {}) => {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})}
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail || response.statusText || "Request failed";
      throw new Error(detail);
    }
    return payload;
  };

  const clearWorkspaceCache = () => {
    [ACCOUNT_KEY, PROFILE_KEY, SAVED_KEY, IGNORED_KEY, DIRTY_KEY].forEach((key) => localStorage.removeItem(key));
    sessionStorage.removeItem("tendergraph.persistenceReloaded");
  };

  const buildDialog = () => {
    const dialog = document.createElement("dialog");
    dialog.className = "auth-dialog";
    dialog.innerHTML = `<div class="auth-dialog-header"><div><p class="eyebrow">ACCOUNT</p><h2>Keep your TenderGraph workspace.</h2></div><button type="button" class="auth-close" aria-label="Close">×</button></div><div class="auth-grid"><form id="auth-login-form" class="auth-form"><h3>Sign in</h3><label>Email <input type="email" name="email" autocomplete="email" required maxlength="320"></label><label>Password <input type="password" name="password" autocomplete="current-password" required maxlength="200"></label><button type="submit">Sign in</button><p class="auth-message" data-auth-message="login" aria-live="polite"></p></form><form id="auth-register-form" class="auth-form"><h3>Create account</h3><p class="auth-copy">Your current local profile and saved pipeline will be attached to this account.</p><label>Name <input type="text" name="display_name" autocomplete="name" maxlength="200"></label><label>Email <input type="email" name="email" autocomplete="email" required maxlength="320"></label><label>Password <input type="password" name="password" autocomplete="new-password" required minlength="12" maxlength="200"></label><label>Confirm password <input type="password" name="confirm_password" autocomplete="new-password" required minlength="12" maxlength="200"></label><button type="submit">Create account</button><p class="auth-message" data-auth-message="register" aria-live="polite"></p></form></div><p class="auth-footnote">Local-first authentication. Use a unique password; public deployment hardening is a later phase.</p>`;
    document.body.appendChild(dialog);
    dialog.querySelector(".auth-close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    return dialog;
  };

  const setMessage = (dialog, kind, text, isError = false) => {
    const node = dialog.querySelector(`[data-auth-message="${kind}"]`);
    node.textContent = text;
    node.classList.toggle("error", isError);
  };

  const attachForms = (dialog) => {
    dialog.querySelector("#auth-login-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      setMessage(dialog, "login", "Signing in…");
      try {
        const result = await request("/auth/login", {method:"POST",body:JSON.stringify({email:data.get("email"),password:data.get("password")})});
        localStorage.setItem(ACCOUNT_KEY, result.account.id);
        localStorage.removeItem(DIRTY_KEY);
        sessionStorage.removeItem("tendergraph.persistenceReloaded");
        location.reload();
      } catch (error) { setMessage(dialog, "login", error.message, true); }
    });
    dialog.querySelector("#auth-register-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      if (data.get("password") !== data.get("confirm_password")) { setMessage(dialog, "register", "Passwords do not match.", true); return; }
      setMessage(dialog, "register", "Creating account…");
      try {
        const result = await request("/auth/register", {method:"POST",body:JSON.stringify({email:data.get("email"),password:data.get("password"),display_name:data.get("display_name") || null,local_account_id:localStorage.getItem(ACCOUNT_KEY) || null})});
        localStorage.setItem(ACCOUNT_KEY, result.account.id);
        sessionStorage.removeItem("tendergraph.persistenceReloaded");
        location.reload();
      } catch (error) { setMessage(dialog, "register", error.message, true); }
    });
  };

  const renderStatus = async () => {
    const topbar = document.querySelector(".topbar");
    if (!topbar) return;
    const slot = document.createElement("div");
    slot.className = "auth-slot";
    topbar.appendChild(slot);
    let status = {authenticated:false};
    try { status = await request("/auth/me"); } catch (error) { console.warn("TenderGraph auth status unavailable", error); }
    if (status.authenticated && status.account) {
      const identity = status.account.display_name || status.account.email || "Account";
      slot.innerHTML = `<span class="auth-identity"></span><button type="button" class="auth-signout">Sign out</button>`;
      slot.querySelector(".auth-identity").textContent = identity;
      slot.querySelector(".auth-signout").addEventListener("click", async () => {
        try { await request("/auth/logout", {method:"POST",body:"{}"}); } catch (error) { console.warn("TenderGraph logout failed", error); }
        clearWorkspaceCache();
        location.reload();
      });
      return;
    }
    const dialog = buildDialog();
    attachForms(dialog);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "auth-open";
    button.textContent = "Sign in / Register";
    button.addEventListener("click", () => dialog.showModal());
    slot.appendChild(button);
  };
  renderStatus();
})();
