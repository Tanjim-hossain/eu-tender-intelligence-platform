"use strict";
(() => {
  const ACCOUNT_KEY = "tendergraph.productAccountId.v1";
  const PROFILE_KEY = "tendergraph.companyProfile.v1";
  const SAVED_KEY = "tendergraph.savedOpportunities.v1";
  const IGNORED_KEY = "tendergraph.ignoredOpportunities.v1";
  const DIRTY_KEY = "tendergraph.persistenceDirty.v1";
  const TRACKED_KEYS = new Set([PROFILE_KEY, SAVED_KEY, IGNORED_KEY]);
  const nativeSetItem = Storage.prototype.setItem;
  const nativeRemoveItem = Storage.prototype.removeItem;
  let accountId = localStorage.getItem(ACCOUNT_KEY);
  let syncTimer = null;
  let hydrating = false;
  let transitioning = false;
  const BASELINE_KEY = "tendergraph.persistenceBaseline.v1";
  let syncChain = Promise.resolve();

  const parse = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  };
  const rawSet = (key, value) => nativeSetItem.call(localStorage, key, value);
  const rawRemove = (key) => nativeRemoveItem.call(localStorage, key);
  const clearWorkspaceCache = () => [PROFILE_KEY, SAVED_KEY, IGNORED_KEY, DIRTY_KEY, BASELINE_KEY].forEach(rawRemove);
  const request = async (path, options = {}) => {
    const response = await fetch(path, {
      credentials: "same-origin",
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
  let publicMode = false;
  const createAccount = async () => {
    if (publicMode) throw new Error("Sign in or register to persist your workspace");
    const account = await request("/product/accounts", {method:"POST"});
    accountId = account.id;
    rawSet(ACCOUNT_KEY, accountId);
    return accountId;
  };
  const authenticatedAccount = async () => {
    try {
      const status = await request("/auth/me");
      return status.authenticated && status.account ? status.account : null;
    } catch (error) {
      console.warn("TenderGraph auth status unavailable", error);
      return null;
    }
  };
  const ensureAccount = async () => {
    if (!accountId) return createAccount();
    try {
      await request(`/product/accounts/${accountId}/state`);
      return accountId;
    } catch (error) {
      if (![401, 403, 404].includes(error.status)) throw error;
      if ([401, 403].includes(error.status)) clearWorkspaceCache();
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
          desired.set(publicationNumber, {disposition:"ignored",pipeline_stage:null,note:"",match_score:null,snapshot:null});
        }
      });
    }
    return desired;
  };
  const baselineOf = (id) => ({accountId:id, profile:parse(PROFILE_KEY, null), opportunities:Object.fromEntries(desiredOpportunityState())});
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const syncNow = async () => {
    if (hydrating || transitioning) return;
    const id = await ensureAccount();
    const state = await request(`/product/accounts/${id}/state`);
    const active = () => !transitioning && accountId === id && localStorage.getItem(ACCOUNT_KEY) === id;
    if (!active()) return;
    const desired = baselineOf(id);
    const previous = parse(BASELINE_KEY, null);
    const baseline = previous?.accountId === id ? previous : null;
    if (!baseline || !same(desired.profile, baseline.profile)) {
      if (desired.profile && typeof desired.profile === "object") {
        await request(`/product/accounts/${id}/profile`, {method:"PUT",body:JSON.stringify(desired.profile)});
      } else if (baseline?.profile && state.profile) {
        await request(`/product/accounts/${id}/profile`, {method:"DELETE"});
      }
    }
    for (const [publicationNumber, value] of Object.entries(desired.opportunities)) {
      if (!active()) return;
      if (baseline && same(value, baseline.opportunities[publicationNumber])) continue;
      await request(`/product/accounts/${id}/opportunities/${encodeURIComponent(publicationNumber)}`, {method:"PUT",body:JSON.stringify(value)});
    }
    // Delete only items known at the previous successful sync.
    for (const publicationNumber of Object.keys(baseline?.opportunities || {})) {
      if (!active()) return;
      if (!Object.hasOwn(desired.opportunities, publicationNumber)) {
        await request(`/product/accounts/${id}/opportunities/${encodeURIComponent(publicationNumber)}`, {method:"DELETE"});
      }
    }
    if (!active()) return;
    rawSet(BASELINE_KEY, JSON.stringify(desired));
    if (same(desired, baselineOf(id))) rawRemove(DIRTY_KEY);
  };
  const queueSync = () => {
    syncChain = syncChain.catch(() => {}).then(syncNow);
    return syncChain;
  };
  window.addEventListener("tendergraph:auth-transition", () => {
    transitioning = true;
    clearTimeout(syncTimer);
  });
  const scheduleSync = () => {
    if (hydrating || transitioning || (publicMode && !accountId)) return;
    rawSet(DIRTY_KEY, "1");
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => queueSync().catch((error) => console.warn("TenderGraph persistence sync failed", error)), 250);
  };
  const hydrate = (state) => {
    hydrating = true;
    try {
      if (state.profile) rawSet(PROFILE_KEY, JSON.stringify(state.profile));
      else rawRemove(PROFILE_KEY);
      const saved = {};
      const ignored = [];
      (state.opportunities || []).forEach((item) => {
        if (item.disposition === "ignored") { ignored.push(item.publication_number); return; }
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
      rawSet(BASELINE_KEY, JSON.stringify(baselineOf(accountId)));
      rawRemove(DIRTY_KEY);
    } finally { hydrating = false; }
  };
  const bootstrap = async () => {
    try { publicMode = Boolean((await request("/config")).public_mode); } catch {}
    const previousAccountId = accountId;
    const registered = await authenticatedAccount();
    if (publicMode && !registered) { clearWorkspaceCache(); rawRemove(ACCOUNT_KEY); accountId = null; return; }
    const switchedAccount = Boolean(registered && previousAccountId && previousAccountId !== registered.id);
    if (registered) { accountId = registered.id; rawSet(ACCOUNT_KEY, accountId); }
    const hadLocalState = Boolean(localStorage.getItem(PROFILE_KEY) || localStorage.getItem(SAVED_KEY) || localStorage.getItem(IGNORED_KEY));
    const locallyDirty = !switchedAccount && localStorage.getItem(DIRTY_KEY) === "1";
    const id = await ensureAccount();
    const state = await request(`/product/accounts/${id}/state`);
    const serverHasState = Boolean(state.profile || (state.opportunities || []).length);
    if (!switchedAccount && (locallyDirty || (hadLocalState && !serverHasState))) { await queueSync(); return; }
    const before = [localStorage.getItem(PROFILE_KEY),localStorage.getItem(SAVED_KEY),localStorage.getItem(IGNORED_KEY)].join("|");
    hydrate(state);
    const after = [localStorage.getItem(PROFILE_KEY),localStorage.getItem(SAVED_KEY),localStorage.getItem(IGNORED_KEY)].join("|");
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
import("/assets/auth.js").catch((error) => console.warn("TenderGraph account controls unavailable", error));
