"use strict";
(() => {
  const ACCOUNT_KEY = "tendergraph.productAccountId.v1";
  const PROFILE_KEY = "tendergraph.companyProfile.v1";
  const SAVED_KEY = "tendergraph.savedOpportunities.v1";
  const IGNORED_KEY = "tendergraph.ignoredOpportunities.v1";
  const TRACKED_KEYS = new Set([PROFILE_KEY, SAVED_KEY, IGNORED_KEY]);
  const nativeSetItem = Storage.prototype.setItem;
  const nativeRemoveItem = Storage.prototype.removeItem;
  let accountId = localStorage.getItem(ACCOUNT_KEY);
  let syncTimer = null;
  let hydrating = false;

  const parse = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  };
  const rawSet = (key, value) => {
    nativeSetItem.call(localStorage, key, value);
  };
  const rawRemove = (key) => {
    nativeRemoveItem.call(localStorage, key);
  };
  const request = async (path, options = {}) => {
    const response = await fetch(path, {
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})}
    });
    if (!response.ok) {
      const detail = await response.text();
      const error = new Error(`${response.status}: ${detail || response.statusText}`);
      error.status = response.status;
      throw error;
    }
    if (response.status === 204) return null;
    return response.json();
  };
  const createAccount = async () => {
    const account = await request("/product/accounts", {method:"POST"});
    accountId = account.id;
    rawSet(ACCOUNT_KEY, accountId);
    return accountId;
  };
  const ensureAccount = async () => {
    if (!accountId) return createAccount();
    try {
      await request(`/product/accounts/${accountId}/state`);
      return accountId;
    } catch (error) {
      if (error.status !== 404) throw error;
      rawRemove(ACCOUNT_KEY);
      accountId = null;
      return createAccount();
    }
  };
  const snapshotFromItem = (item) => ({
    title: item.title || "Untitled tender",
    buyer_name: item.buyer_name || null,
    buyer_country: item.buyer_country || "—",
    estimated_value: item.estimated_value ?? null,
    estimated_value_currency: item.estimated_value_currency || null,
    earliest_deadline: item.earliest_deadline || null,
    source_html_url: item.source_html_url || "https://ted.europa.eu/"
  });
  const desiredOpportunityState = () => {
    const desired = new Map();
    const saved = parse(SAVED_KEY, {});
    if (saved && typeof saved === "object" && !Array.isArray(saved)) {
      Object.entries(saved).forEach(([publicationNumber, item]) => {
        if (!item || typeof item !== "object") return;
        desired.set(publicationNumber, {
          disposition:"saved",
          pipeline_stage:["reviewing","qualified","bid","no_bid"].includes(item.stage) ? item.stage : "reviewing",
          note:String(item.note || "").slice(0, 5000),
          match_score:Number.isFinite(Number(item.match_score)) ? Number(item.match_score) : null,
          snapshot:snapshotFromItem(item)
        });
      });
    }
    const ignored = parse(IGNORED_KEY, []);
    if (Array.isArray(ignored)) {
      ignored.forEach((publicationNumber) => {
        if (!desired.has(publicationNumber)) {
          desired.set(publicationNumber, {
            disposition:"ignored",
            pipeline_stage:null,
            note:"",
            match_score:null,
            snapshot:null
          });
        }
      });
    }
    return desired;
  };
  const syncNow = async () => {
    if (hydrating) return;
    const id = await ensureAccount();
    const state = await request(`/product/accounts/${id}/state`);
    const profile = parse(PROFILE_KEY, null);
    if (profile && typeof profile === "object") {
      await request(`/product/accounts/${id}/profile`, {
        method:"PUT",
        body:JSON.stringify(profile)
      });
    }
    const desired = desiredOpportunityState();
    for (const [publicationNumber, value] of desired) {
      await request(`/product/accounts/${id}/opportunities/${encodeURIComponent(publicationNumber)}`, {
        method:"PUT",
        body:JSON.stringify(value)
      });
    }
    const serverNumbers = new Set((state.opportunities || []).map((item) => item.publication_number));
    for (const publicationNumber of serverNumbers) {
      if (!desired.has(publicationNumber)) {
        await request(`/product/accounts/${id}/opportunities/${encodeURIComponent(publicationNumber)}`, {
          method:"DELETE"
        });
      }
    }
  };
  const scheduleSync = () => {
    if (hydrating) return;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => {
      syncNow().catch((error) => console.warn("TenderGraph persistence sync failed", error));
    }, 250);
  };
  const hydrate = (state) => {
    hydrating = true;
    try {
      if (state.profile) rawSet(PROFILE_KEY, JSON.stringify(state.profile));
      const saved = {};
      const ignored = [];
      (state.opportunities || []).forEach((item) => {
        if (item.disposition === "ignored") {
          ignored.push(item.publication_number);
          return;
        }
        if (!item.snapshot) return;
        saved[item.publication_number] = {
          publication_number:item.publication_number,
          ...item.snapshot,
          match_score:item.match_score,
          stage:item.pipeline_stage || "reviewing",
          note:item.note || "",
          saved_at:item.created_at,
          updated_at:item.updated_at
        };
      });
      rawSet(SAVED_KEY, JSON.stringify(saved));
      rawSet(IGNORED_KEY, JSON.stringify(ignored));
    } finally {
      hydrating = false;
    }
  };
  const bootstrap = async () => {
    const hadAccount = Boolean(accountId);
    const hadLocalState = Boolean(
      localStorage.getItem(PROFILE_KEY)
      || localStorage.getItem(SAVED_KEY)
      || localStorage.getItem(IGNORED_KEY)
    );
    const id = await ensureAccount();
    if (!hadAccount && hadLocalState) {
      await syncNow();
      return;
    }
    const state = await request(`/product/accounts/${id}/state`);
    const before = [
      localStorage.getItem(PROFILE_KEY),
      localStorage.getItem(SAVED_KEY),
      localStorage.getItem(IGNORED_KEY)
    ].join("|");
    hydrate(state);
    const after = [
      localStorage.getItem(PROFILE_KEY),
      localStorage.getItem(SAVED_KEY),
      localStorage.getItem(IGNORED_KEY)
    ].join("|");
    if (before !== after && !sessionStorage.getItem("tendergraph.persistenceReloaded")) {
      sessionStorage.setItem("tendergraph.persistenceReloaded", "1");
      location.reload();
    }
  };

  Storage.prototype.setItem = function(key, value) {
    nativeSetItem.call(this, key, value);
    if (this === localStorage && TRACKED_KEYS.has(key)) scheduleSync();
  };
  Storage.prototype.removeItem = function(key) {
    nativeRemoveItem.call(this, key);
    if (this === localStorage && TRACKED_KEYS.has(key)) scheduleSync();
  };

  bootstrap().catch((error) => console.warn("TenderGraph persistence unavailable; using browser cache", error));
})();
