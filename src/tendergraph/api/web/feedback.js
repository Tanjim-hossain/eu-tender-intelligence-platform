"use strict";
(() => {
  const SAVED_KEY = "tendergraph.savedOpportunities.v1";
  const IGNORED_KEY = "tendergraph.ignoredOpportunities.v1";
  const nativeFetch = window.fetch.bind(window);
  let latestMatches = [];
  let enhanceTimer = null;
  const initialSavedView = location.hash === "#saved";

  const $ = (id) => document.getElementById(id);
  const read = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  };
  const write = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  };
  const saved = () => {
    const value = read(SAVED_KEY, {});
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  };
  const ignored = () => {
    const value = read(IGNORED_KEY, []);
    return new Set(Array.isArray(value) ? value : []);
  };
  const safeTedUrl = (raw) => {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" && url.hostname === "ted.europa.eu" ? url.href : null;
    } catch {
      return null;
    }
  };
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const displayDate = (raw) => {
    if (!raw) return "Not stated";
    const value = new Date(raw);
    return Number.isNaN(value.getTime()) ? "Not stated" : value.toLocaleDateString("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"});
  };
  const displayValue = (value, currency) => {
    if (value == null) return "Not stated";
    const number = Number(value);
    const amount = Number.isFinite(number) ? new Intl.NumberFormat("en", {maximumFractionDigits:0}).format(number) : String(value);
    return `${currency || ""} ${amount}`.trim();
  };

  function updateCounts() {
    const savedCount = Object.keys(saved()).length;
    const ignoredCount = ignored().size;
    [["saved-count", savedCount], ["ignored-count", ignoredCount], ["saved-nav-count", savedCount], ["mobile-saved-count", savedCount], ["saved-workspace-count", savedCount]].forEach(([id, value]) => {
      const node = $(id); if (node) node.textContent = String(value);
    });
  }

  function toggleSaved(item, button) {
    const state = saved();
    if (state[item.publication_number]) delete state[item.publication_number];
    else state[item.publication_number] = {...item, saved_at:new Date().toISOString()};
    write(SAVED_KEY, state);
    updateCounts();
    const active = Boolean(state[item.publication_number]);
    button.textContent = active ? "Saved ✓" : "Save opportunity";
    button.classList.toggle("saved", active);
    renderSaved();
  }

  function ignoreItem(item) {
    const state = ignored();
    state.add(item.publication_number);
    write(IGNORED_KEY, [...state]);
    const savedState = saved();
    if (savedState[item.publication_number]) {
      delete savedState[item.publication_number];
      write(SAVED_KEY, savedState);
    }
    updateCounts();
    scheduleEnhance();
    renderSaved();
  }

  function scheduleEnhance() {
    clearTimeout(enhanceTimer);
    enhanceTimer = setTimeout(enhanceMatches, 0);
  }

  function enhanceMatches() {
    const container = $("match-results");
    if (!container || !latestMatches.length) return;
    const cards = [...container.querySelectorAll(".match-card")];
    if (!cards.length) return;
    const ignoredState = ignored();
    const savedState = saved();
    let visible = 0;
    cards.forEach((card, index) => {
      const item = latestMatches[index];
      if (!item) return;
      const hidden = ignoredState.has(item.publication_number);
      card.hidden = hidden;
      if (hidden) return;
      visible += 1;
      let actions = card.querySelector(".match-actions");
      if (!actions) {
        actions = make("div", null, "match-actions");
        const saveButton = make("button", "Save opportunity", "save-button");
        saveButton.type = "button";
        saveButton.addEventListener("click", () => toggleSaved(item, saveButton));
        const ignoreButton = make("button", "Not relevant", "ignore-button");
        ignoreButton.type = "button";
        ignoreButton.addEventListener("click", () => ignoreItem(item));
        actions.append(saveButton, ignoreButton);
        const bottom = card.querySelector(".card-bottom");
        if (bottom) card.insertBefore(actions, bottom); else card.append(actions);
      }
      const saveButton = actions.querySelector(".save-button");
      const active = Boolean(savedState[item.publication_number]);
      if (saveButton) {
        saveButton.textContent = active ? "Saved ✓" : "Save opportunity";
        saveButton.classList.toggle("saved", active);
      }
    });
    const count = $("match-count");
    if (count) count.textContent = String(visible);
    updateCounts();
  }

  function renderSaved() {
    const container = $("saved-results");
    if (!container) return;
    const items = Object.values(saved()).sort((a, b) => String(b.saved_at || "").localeCompare(String(a.saved_at || "")));
    container.replaceChildren();
    if (!items.length) {
      const empty = make("div", null, "empty-state saved-empty");
      empty.append(make("span", "☆", "empty-icon"), make("h3", "No saved opportunities yet."), make("p", "Save promising tenders from Company Matches to build a shortlist for review."));
      container.append(empty);
      updateCounts();
      return;
    }
    items.forEach((item) => {
      const card = make("article", null, "saved-card");
      const top = make("div", null, "saved-card-top");
      const meta = make("div", null, "saved-meta");
      meta.append(make("span", item.buyer_country || "—"), make("span", "·"), make("span", item.publication_number));
      top.append(meta, make("span", `${Math.round(item.match_score || 0)}% fit`, "saved-score"));
      const fields = make("div", null, "saved-card-fields");
      fields.append(make("span", item.buyer_name || "Buyer not stated"), make("span", `Deadline: ${displayDate(item.earliest_deadline)}`), make("span", `Value: ${displayValue(item.estimated_value, item.estimated_value_currency)}`));
      const actions = make("div", null, "saved-card-actions");
      const url = safeTedUrl(item.source_html_url);
      if (url) {
        const link = make("a", "Open TED notice ↗"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; actions.append(link);
      }
      const remove = make("button", "Remove", "ignore-button");
      remove.type = "button";
      remove.addEventListener("click", () => {
        const state = saved(); delete state[item.publication_number]; write(SAVED_KEY, state); renderSaved(); scheduleEnhance();
      });
      actions.append(remove);
      card.append(top, make("h3", item.title || "Untitled tender", "card-title"), fields, actions);
      container.append(card);
    });
    updateCounts();
  }

  function showSaved() {
    const matches = $("match-workspace"); const explorer = $("explorer-workspace"); const savedWorkspace = $("saved-workspace");
    if (!savedWorkspace) return;
    if (matches) matches.hidden = true;
    if (explorer) explorer.hidden = true;
    savedWorkspace.hidden = false;
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === "saved";
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    renderSaved();
    if (location.hash !== "#saved") history.replaceState(null, "", "#saved");
  }

  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const target = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
    if (target.endsWith("/matches") && response.ok) {
      response.clone().json().then((data) => {
        latestMatches = Array.isArray(data.matches) ? data.matches : [];
        scheduleEnhance();
      }).catch(() => {});
    }
    return response;
  };

  document.querySelectorAll('[data-view="saved"]').forEach((button) => {
    button.addEventListener("click", (event) => { event.stopImmediatePropagation(); showSaved(); });
  });
  document.querySelectorAll('[data-view="matches"], [data-view="explorer"]').forEach((button) => {
    button.addEventListener("click", () => { const workspace = $("saved-workspace"); if (workspace) workspace.hidden = true; });
  });
  $("reset-ignored")?.addEventListener("click", () => { write(IGNORED_KEY, []); updateCounts(); scheduleEnhance(); });
  $("clear-saved")?.addEventListener("click", () => { write(SAVED_KEY, {}); renderSaved(); scheduleEnhance(); });

  const matchResults = $("match-results");
  if (matchResults) new MutationObserver(scheduleEnhance).observe(matchResults, {childList:true});
  updateCounts();
  renderSaved();
  if (initialSavedView) setTimeout(showSaved, 0);
})();
