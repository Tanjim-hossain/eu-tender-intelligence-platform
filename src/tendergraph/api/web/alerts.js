"use strict";
(() => {
  const ACCOUNT_KEY = "tendergraph.productAccountId.v1";
  const SAVED_KEY = "tendergraph.savedOpportunities.v1";
  const IGNORED_KEY = "tendergraph.ignoredOpportunities.v1";
  const $ = (id) => document.getElementById(id);

  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/assets/alerts.css";
  document.head.appendChild(stylesheet);

  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const parse = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  };
  const request = async (path, options = {}) => {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})}
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail || response.statusText || "Request failed";
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return payload;
  };
  const safeTedUrl = (raw) => {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" && url.hostname === "ted.europa.eu" ? url.href : null;
    } catch {
      return null;
    }
  };
  const displayDate = (raw) => {
    if (!raw) return "Not stated";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return "Not stated";
    return date.toLocaleDateString("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
  };
  const displayDateTime = (raw) => {
    if (!raw) return "Never";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return "Never";
    return date.toLocaleString("en-GB", {day:"numeric", month:"short", hour:"2-digit", minute:"2-digit"});
  };
  const displayValue = (value, currency) => {
    if (value == null) return "Not stated";
    const numeric = Number(value);
    const amount = Number.isFinite(numeric) ? new Intl.NumberFormat("en", {maximumFractionDigits:0}).format(numeric) : String(value);
    return `${currency || ""} ${amount}`.trim();
  };

  const sidebarNav = document.querySelector(".workspace-nav");
  const mobileNav = document.querySelector(".mobile-nav");
  const main = document.querySelector("main");
  if (!sidebarNav || !mobileNav || !main) return;

  const nav = make("button", null, "nav-item");
  nav.id = "nav-alerts";
  nav.type = "button";
  nav.dataset.view = "alerts";
  nav.setAttribute("aria-controls", "alerts-workspace");
  nav.innerHTML = '<span aria-hidden="true">◉</span> New tender alerts <span id="alerts-nav-count" class="nav-count">0</span>';
  sidebarNav.append(nav);

  const mobile = make("button");
  mobile.type = "button";
  mobile.dataset.view = "alerts";
  mobile.setAttribute("aria-controls", "alerts-workspace");
  mobile.innerHTML = 'Alerts <span id="mobile-alerts-count">0</span>';
  mobileNav.append(mobile);

  const workspace = make("section", null, "workspace");
  workspace.id = "alerts-workspace";
  workspace.hidden = true;
  workspace.setAttribute("aria-labelledby", "alerts-title");
  workspace.innerHTML = `
    <div class="intro">
      <p class="eyebrow">PERSONALIZED TENDER ALERTS</p>
      <h1 id="alerts-title">See what is newly relevant to your company.</h1>
      <p>TenderGraph reuses your company profile to detect recent, high-fit opportunities and keeps a deduplicated digest for review.</p>
    </div>
    <div class="alerts-layout">
      <section class="alerts-settings" aria-labelledby="alerts-settings-title">
        <p class="eyebrow">ALERT SETTINGS</p>
        <h2 id="alerts-settings-title">Control your signal threshold.</h2>
        <p class="alerts-settings-copy">Only recent, open tenders above your fit threshold are eligible. Saved and ignored opportunities are excluded from future detections.</p>
        <form id="alerts-form" class="alerts-form">
          <label class="alerts-switch"><input id="alerts-enabled" type="checkbox" checked> Enable personalized alert detection</label>
          <label class="alerts-field">Minimum profile-fit score
            <input id="alerts-min-score" type="number" min="0" max="100" step="1" value="70">
          </label>
          <label class="alerts-field">Recent notice window
            <select id="alerts-lookback"><option value="7">7 days</option><option value="14" selected>14 days</option><option value="30">30 days</option><option value="60">60 days</option><option value="90">90 days</option></select>
          </label>
          <label class="alerts-field">Digest size
            <select id="alerts-max-items"><option value="5">5 items</option><option value="10" selected>10 items</option><option value="20">20 items</option><option value="50">50 items</option></select>
          </label>
          <div class="alerts-actions"><button type="submit">Save alert settings</button></div>
        </form>
        <p id="alerts-settings-status" class="alerts-status" aria-live="polite"></p>
        <div class="alerts-boundary">v1 stores alerts inside TenderGraph and can be refreshed through the API or local scheduler. No paid email/SMS provider is required.</div>
      </section>
      <section class="alerts-digest" aria-labelledby="alerts-digest-title">
        <div class="alerts-toolbar">
          <div><p class="eyebrow">CURRENT DIGEST</p><h2 id="alerts-digest-title">New opportunities</h2><p id="alerts-last-refresh" class="alerts-digest-copy">Last refresh: never</p></div>
          <div class="alerts-toolbar-actions"><button id="alerts-mark-all" class="secondary" type="button">Mark all reviewed</button><button id="alerts-refresh" type="button">Refresh alerts →</button></div>
        </div>
        <div class="alerts-summary"><span><strong id="alerts-unread-count">0</strong> unread</span><span><strong id="alerts-total-count">0</strong> detected</span><span>Recent open notices only</span></div>
        <p id="alerts-status" class="alerts-status" aria-live="polite"></p>
        <div id="alerts-results" class="alerts-results" aria-live="polite"><div class="alerts-empty">Set up a company profile, then refresh alerts to build your personalized digest.</div></div>
      </section>
    </div>`;
  main.insertBefore(workspace, main.querySelector("footer"));

  let accountId = null;
  let preferences = null;
  let loading = false;

  const setCount = (count) => {
    const value = String(count || 0);
    if ($("alerts-nav-count")) $("alerts-nav-count").textContent = value;
    if ($("mobile-alerts-count")) $("mobile-alerts-count").textContent = value;
    if ($("alerts-unread-count")) $("alerts-unread-count").textContent = value;
  };
  const status = (message, isError = false) => {
    const node = $("alerts-status");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("error", isError);
  };
  const settingsStatus = (message, isError = false) => {
    const node = $("alerts-settings-status");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("error", isError);
  };
  const fillPreferences = (value) => {
    preferences = value;
    $("alerts-enabled").checked = Boolean(value.enabled);
    $("alerts-min-score").value = String(value.min_match_score ?? 70);
    $("alerts-lookback").value = String(value.lookback_days ?? 14);
    $("alerts-max-items").value = String(value.max_items ?? 10);
    $("alerts-last-refresh").textContent = `Last refresh: ${displayDateTime(value.last_refreshed_at)}`;
  };

  const markSeen = async (publicationNumber) => {
    if (!accountId) return;
    await request(`/alerts/accounts/${accountId}/items/${encodeURIComponent(publicationNumber)}/seen`, {method:"POST", body:"{}"});
  };

  const saveOpportunity = async (item) => {
    const saved = parse(SAVED_KEY, {});
    const state = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    state[item.publication_number] = {
      publication_number:item.publication_number,
      title:item.title,
      buyer_name:item.buyer_name,
      buyer_country:item.buyer_country,
      estimated_value:item.estimated_value,
      estimated_value_currency:item.estimated_value_currency,
      earliest_deadline:item.earliest_deadline,
      source_html_url:item.source_html_url,
      match_score:item.match_score,
      stage:"reviewing",
      note:"",
      saved_at:new Date().toISOString()
    };
    localStorage.setItem(SAVED_KEY, JSON.stringify(state));
    await markSeen(item.publication_number);
    await loadDigest();
  };

  const ignoreOpportunity = async (item) => {
    const values = parse(IGNORED_KEY, []);
    const ignored = new Set(Array.isArray(values) ? values : []);
    ignored.add(item.publication_number);
    localStorage.setItem(IGNORED_KEY, JSON.stringify([...ignored]));
    await markSeen(item.publication_number);
    await loadDigest();
  };

  const renderDigest = (digest) => {
    setCount(digest.unread_count);
    $("alerts-total-count").textContent = String(digest.total_count || 0);
    $("alerts-last-refresh").textContent = `Last refresh: ${displayDateTime(digest.last_refreshed_at)}`;
    const container = $("alerts-results");
    container.replaceChildren();
    if (!digest.items?.length) {
      container.append(make("div", "No matching alerts are stored yet. Refresh after new TED data is loaded, or lower the fit threshold.", "alerts-empty"));
      return;
    }
    digest.items.forEach((item) => {
      const unread = !item.seen_at;
      const card = make("article", null, `alert-card${unread ? " unread" : ""}`);
      const top = make("div", null, "alert-card-top");
      const meta = make("div", null, "alert-meta");
      if (unread) meta.append(make("span", "New", "alert-unread-pill"));
      meta.append(make("span", item.buyer_country || "—"), make("span", "·"), make("span", item.publication_number), make("span", "·"), make("span", `Published ${displayDate(item.publication_date)}`));
      top.append(meta, make("span", `${Math.round(item.match_score)}% fit`, "alert-score"));
      const fields = make("div", null, "alert-fields");
      [["Buyer", item.buyer_name || "Not stated"], ["Deadline", displayDate(item.earliest_deadline)], ["Estimated value", displayValue(item.estimated_value, item.estimated_value_currency)]].forEach(([label, value]) => {
        const group = make("span");
        group.append(make("small", label), document.createTextNode(value));
        fields.append(group);
      });
      card.append(top, make("h3", item.title || "Untitled tender"), fields);
      if (item.why_matches?.length) {
        const reasons = make("ul", null, "alert-reasons");
        item.why_matches.slice(0, 3).forEach((reason) => reasons.append(make("li", reason)));
        card.append(reasons);
      }
      const actions = make("div", null, "alert-card-actions");
      const url = safeTedUrl(item.source_html_url);
      if (url) {
        const link = make("a", "Open TED notice ↗");
        link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
        link.addEventListener("click", () => { markSeen(item.publication_number).then(loadDigest).catch(() => {}); });
        actions.append(link);
      }
      const save = make("button", "Save opportunity", "secondary");
      save.type = "button";
      save.addEventListener("click", () => saveOpportunity(item).catch((error) => status(error.message, true)));
      const ignore = make("button", "Not relevant", "secondary");
      ignore.type = "button";
      ignore.addEventListener("click", () => ignoreOpportunity(item).catch((error) => status(error.message, true)));
      actions.append(save, ignore);
      if (unread) {
        const reviewed = make("button", "Mark reviewed", "secondary");
        reviewed.type = "button";
        reviewed.addEventListener("click", () => markSeen(item.publication_number).then(loadDigest).catch((error) => status(error.message, true)));
        actions.append(reviewed);
      }
      card.append(actions);
      container.append(card);
    });
  };

  const loadPreferences = async () => {
    if (!accountId) return;
    const value = await request(`/alerts/accounts/${accountId}/preferences`);
    fillPreferences(value);
  };
  async function loadDigest() {
    if (!accountId) return;
    try {
      const digest = await request(`/alerts/accounts/${accountId}/digest`);
      renderDigest(digest);
      status("");
    } catch (error) {
      if (error.status === 409) {
        setCount(0);
        $("alerts-results").replaceChildren(make("div", "Create and save your company profile first. Alerts use that profile as the matching definition.", "alerts-empty"));
        status(error.message, true);
        return;
      }
      status(error.message, true);
    }
  }

  const refresh = async () => {
    if (!accountId || loading) return;
    loading = true;
    $("alerts-refresh").disabled = true;
    status("Matching recent TED notices against your company profile…");
    try {
      const result = await request(`/alerts/accounts/${accountId}/refresh`, {method:"POST", body:"{}"});
      renderDigest(result.digest);
      status(result.new_count ? `${result.new_count} new relevant tender${result.new_count === 1 ? "" : "s"} added to your digest.` : "No new qualifying tenders found in the current recent-notice window.");
      await loadPreferences();
    } catch (error) {
      status(error.message, true);
    } finally {
      loading = false;
      $("alerts-refresh").disabled = false;
    }
  };

  const showAlerts = () => {
    ["match-workspace", "explorer-workspace", "saved-workspace"].forEach((id) => {const node = $(id); if (node) node.hidden = true;});
    workspace.hidden = false;
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === "alerts";
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    if (location.hash !== "#alerts") history.replaceState(null, "", "#alerts");
    loadDigest().catch(() => {});
  };

  [nav, mobile].forEach((button) => button.addEventListener("click", (event) => {event.stopImmediatePropagation(); showAlerts();}));
  document.querySelectorAll('[data-view="matches"], [data-view="explorer"], [data-view="saved"]').forEach((button) => {
    button.addEventListener("click", () => {workspace.hidden = true;});
  });

  $("alerts-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!accountId) return;
    settingsStatus("Saving…");
    try {
      const payload = {
        enabled:$("alerts-enabled").checked,
        min_match_score:Number($("alerts-min-score").value),
        lookback_days:Number($("alerts-lookback").value),
        max_items:Number($("alerts-max-items").value)
      };
      fillPreferences(await request(`/alerts/accounts/${accountId}/preferences`, {method:"PUT", body:JSON.stringify(payload)}));
      settingsStatus("Alert settings saved.");
      await loadDigest();
    } catch (error) {
      settingsStatus(error.message, true);
    }
  });
  $("alerts-refresh").addEventListener("click", refresh);
  $("alerts-mark-all").addEventListener("click", async () => {
    if (!accountId) return;
    try {
      await request(`/alerts/accounts/${accountId}/seen-all`, {method:"POST", body:"{}"});
      await loadDigest();
    } catch (error) {
      status(error.message, true);
    }
  });

  const bootstrap = async (attempt = 0) => {
    accountId = localStorage.getItem(ACCOUNT_KEY);
    if (!accountId) {
      if (attempt < 20) {
        setTimeout(() => bootstrap(attempt + 1), 250);
        return;
      }
      settingsStatus("Product account is not ready. Reload the page after the local database is available.", true);
      return;
    }
    try {
      await loadPreferences();
      await loadDigest();
    } catch (error) {
      settingsStatus(error.message, true);
    }
  };

  bootstrap();
  if (location.hash === "#alerts") setTimeout(showAlerts, 0);
})();
