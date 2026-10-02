"use strict";
const $ = (id) => document.getElementById(id);
const PROFILE_STORAGE_KEY = "tendergraph.companyProfile.v1";
let lastAnswer = null;
let busy = false;
const statusLabels = {answered: "Answer with citations", evidence_only: "Retrieved evidence", no_results: "No notices found", insufficient_evidence: "Insufficient evidence"};
function el(tag, text, className) {const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node;}
function sourceURL(raw) {try {const url = new URL(raw); return url.protocol === "https:" && url.hostname === "ted.europa.eu" ? url.href : null;} catch {return null;}}
function sourceLink(raw, text, className) {const url = sourceURL(raw); const node = el(url ? "a" : "span", text, className); if (url) {node.href = url; node.target = "_blank"; node.rel = "noopener noreferrer";} return node;}
function notify(message) {$("notice").textContent = message; $("notice").hidden = !message;}
function pending(value) {
  busy = value;
  ["search-button", "ask-button", "match-button"].forEach(id => {$(id).disabled = value;});
  ["search-form", "ask-form", "profile-form"].forEach(id => $(id).setAttribute("aria-busy", String(value)));
}
async function request(path, payload) {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 660000);
  try {
    const response = await fetch(path, {method: payload ? "POST" : "GET", headers: payload ? {"Content-Type": "application/json"} : {}, body: payload ? JSON.stringify(payload) : undefined, signal: controller.signal});
    let body; try {body = await response.json();} catch {throw new Error("The server returned an unreadable response.");}
    if (!response.ok) {const detail = typeof body.detail === "string" ? body.detail : "Check your inputs and try again."; throw new Error(`${response.status}: ${detail}`);}
    return body;
  } catch (error) {if (error.name === "AbortError") throw new Error("The request timed out. Check the local model and try fewer candidate notices."); if (error instanceof TypeError) throw new Error("Cannot reach TenderGraph. Check that the local server is running."); throw error;}
  finally {clearTimeout(timer);}
}
function displayDate(raw) {if (!raw) return "Not stated"; const date = new Date(raw); return Number.isNaN(date.getTime()) ? "Not stated" : date.toLocaleDateString("en-GB", {day:"numeric", month:"short", year:"numeric", timeZone:"UTC"}) + (raw.includes("T") ? " · UTC" : "");}
function displayValue(value, currency) {if (value == null) return "Not stated"; const numeric = Number(value); const amount = Number.isFinite(numeric) ? new Intl.NumberFormat("en", {maximumFractionDigits:0}).format(numeric) : String(value); return `${currency || ""} ${amount}`.trim();}
function showWorkspace(view) {
  const matches = view !== "explorer";
  $("match-workspace").hidden = !matches;
  $("explorer-workspace").hidden = matches;
  const activeView = matches ? "matches" : "explorer";
  document.querySelectorAll("[data-view]").forEach(button => {
    const active = button.dataset.view === activeView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  const hash = matches ? "#matches" : "#explorer";
  if (location.hash !== hash) history.replaceState(null, "", hash);
  notify("");
}
function parseTerms(raw) {return [...new Set(raw.split(/[\n,;]+/).map(item => item.trim()).filter(Boolean))];}
function optionalNumber(id) {const raw = $(id).value.trim(); return raw === "" ? null : Number(raw);}
function buildProfile() {
  const services = parseTerms($("company-services").value);
  if (!$("company-name").value.trim()) throw new Error("Company name is required.");
  if (!services.length) throw new Error("Add at least one service your company provides.");
  const targetCountries = parseTerms($("target-countries").value).map(item => item.toUpperCase());
  if (targetCountries.some(country => country.length !== 3)) throw new Error("Target countries must use three-letter codes such as BEL, NLD or DEU.");
  const minimum = optionalNumber("preferred-min-value");
  const maximum = optionalNumber("preferred-max-value");
  if ((minimum != null && minimum < 0) || (maximum != null && maximum < 0)) throw new Error("Preferred contract values cannot be negative.");
  if (minimum != null && maximum != null && minimum > maximum) throw new Error("Minimum contract value cannot exceed maximum contract value.");
  return {
    company_name: $("company-name").value.trim(),
    description: $("company-description").value.trim() || null,
    services,
    technologies: parseTerms($("company-technologies").value),
    industries: parseTerms($("company-industries").value),
    keywords: parseTerms($("company-keywords").value),
    target_countries: targetCountries,
    preferred_min_value: minimum,
    preferred_max_value: maximum,
    preferred_value_currency: $("preferred-currency").value,
    min_days_to_deadline: Number($("min-days").value)
  };
}
function fillProfile(profile) {
  $("company-name").value = profile.company_name || "";
  $("company-description").value = profile.description || "";
  $("company-services").value = (profile.services || []).join(", ");
  $("company-technologies").value = (profile.technologies || []).join(", ");
  $("company-industries").value = (profile.industries || []).join(", ");
  $("company-keywords").value = (profile.keywords || []).join(", ");
  $("target-countries").value = (profile.target_countries || []).join(", ");
  $("preferred-min-value").value = profile.preferred_min_value ?? "";
  $("preferred-max-value").value = profile.preferred_max_value ?? "";
  $("preferred-currency").value = profile.preferred_value_currency || "EUR";
  $("min-days").value = String(profile.min_days_to_deadline ?? 7);
}
function saveProfile(profile) {try {localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));} catch {}}
function restoreProfile() {try {const raw = localStorage.getItem(PROFILE_STORAGE_KEY); if (raw) fillProfile(JSON.parse(raw));} catch {}}
function reasonList(title, items, className) {
  const block = el("div", null, `signal-block ${className}`); block.append(el("strong", title));
  const list = el("ul"); items.forEach(item => list.append(el("li", item))); block.append(list); return block;
}
function renderMatches(data) {
  $("match-results").replaceChildren(); $("match-count").textContent = data.count;
  $("match-caption").textContent = data.count ? `Ranked for ${data.profile_name} · candidate query: “${data.query}”` : `No recommended opportunities found for ${data.profile_name}.`;
  if (!data.count) {const empty = el("div", null, "empty-state match-empty"); empty.append(el("h3", "No matching opportunities in the loaded dataset."), el("p", "Broaden the services, technologies or target markets in your profile and try again.")); $("match-results").append(empty); return;}
  data.matches.forEach((item, index) => {
    const card = el("article", null, "match-card");
    const top = el("div", null, "match-card-top");
    const identity = el("div", null, "match-identity"); identity.append(el("span", String(index + 1).padStart(2,"0"), "rank"), el("span", item.buyer_country), el("span", "·"), el("span", item.publication_number));
    const scoreClass = item.match_score >= 80 ? "score-high" : item.match_score >= 60 ? "score-mid" : "score-low";
    const score = el("div", null, `fit-score ${scoreClass}`); score.append(el("strong", `${Math.round(item.match_score)}%`), el("span", "profile fit"));
    top.append(identity, score);
    const fields = el("dl", null, "card-fields");
    [["BUYER", item.buyer_name || "Not stated"], ["DEADLINE", displayDate(item.earliest_deadline)], ["ESTIMATED VALUE", displayValue(item.estimated_value, item.estimated_value_currency)], ["PUBLISHED", displayDate(item.publication_date)]].forEach(([label, text]) => {const group = el("div"); group.append(el("dt",label),el("dd",text)); fields.append(group);});
    const signals = el("div", null, "signal-grid");
    if (item.why_matches.length) signals.append(reasonList("Why it matches", item.why_matches, "positive"));
    if (item.risks.length) signals.append(reasonList("Review before bidding", item.risks, "risk"));
    const bottom = el("div", null, "card-bottom"); bottom.append(sourceLink(item.source_html_url, "Open official TED notice ↗"), el("span", "Fit is a triage signal · verify eligibility"));
    card.append(top, el("h3", item.title, "card-title"), fields, signals, bottom); $("match-results").append(card);
  });
}
function renderResults(data) {
  $("results").replaceChildren(); $("result-count").textContent = data.count;
  if (!data.count) {const empty = el("div", null, "empty-state"); empty.append(el("h3", "No matching notices found."), el("p", "Try a broader topic or a different service name.")); $("results").append(empty); return;}
  data.results.forEach((item, index) => {
    const card = el("article", null, "tender-card"); const top = el("div", null, "card-top"); top.append(el("span", String(index + 1).padStart(2,"0"), "rank"), el("span", item.buyer_country), el("span", "·"), el("span", item.publication_number));
    const fields = el("dl", null, "card-fields");
    [["BUYER", item.buyer_name || "Not stated"], ["DEADLINE", displayDate(item.earliest_deadline)], ["ESTIMATED VALUE", displayValue(item.estimated_value, item.estimated_value_currency)], ["PUBLISHED", displayDate(item.publication_date)]].forEach(([label, text]) => {const group = el("div"); group.append(el("dt",label),el("dd",text)); fields.append(group);});
    const bottom = el("div", null, "card-bottom"); bottom.append(sourceLink(item.source_html_url, "Open TED notice ↗"), el("span", "Search match · verify relevance"));
    card.append(top, el("h3", item.title, "card-title"), fields, bottom); $("results").append(card);
  });
}
$("profile-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (busy) return; notify("");
  let profile; try {profile = buildProfile();} catch(error) {notify(error.message); return;}
  pending(true); $("match-results").replaceChildren(el("p", "Ranking the loaded tender dataset for your company…", "loading")); $("match-count").textContent = "…"; $("match-time").textContent = "";
  const started = performance.now();
  try {const limit = Number($("match-limit").value); const data = await request("/matches", {profile, limit, retrieval_depth:Math.max(50,limit)}); saveProfile(profile); renderMatches(data); $("match-time").textContent = `${((performance.now()-started)/1000).toFixed(1)}s`;}
  catch(error) {notify(error.message); $("match-count").textContent = "—"; $("match-results").replaceChildren(el("p", "Personalized matching could not be completed. Your company profile has been kept.", "loading"));}
  finally {pending(false);}
});
$("example-profile").addEventListener("click", () => {
  if (busy) return;
  fillProfile({company_name:"Example Data Studio", description:"Data and AI consultancy serving public-sector organizations", services:["Data engineering","BI analytics","machine learning"], technologies:["Python","Azure","Power BI"], industries:["Healthcare","public sector"], keywords:["cloud platform","data lakehouse"], target_countries:["BEL","NLD","DEU","ITA"], preferred_min_value:50000, preferred_max_value:1000000, preferred_value_currency:"EUR", min_days_to_deadline:7});
  $("company-name").focus(); notify("");
});
$("search-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (busy) return; const query = $("query").value.trim(); if (!query) return;
  notify(""); pending(true); $("answer-output").hidden = true; lastAnswer = null;
  $("results").replaceChildren(el("p", "Searching the loaded tender dataset…", "loading")); $("result-count").textContent = "…"; $("search-time").textContent = "";
  const started = performance.now();
  try {const limit = Number($("limit").value); const data = await request("/search", {query, limit, retrieval_depth:Math.max(20,limit)}); renderResults(data); $("results-caption").textContent = `Matches for “${data.query}” · ranked by lexical and semantic similarity`; $("search-time").textContent = `${((performance.now()-started)/1000).toFixed(1)}s`;}
  catch(error) {notify(error.message); $("result-count").textContent = "—"; $("results").replaceChildren(el("p", "Search could not be completed. Your question and query have been kept.", "loading"));}
  finally {pending(false);}
});
$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (busy) return; const question = $("question").value.trim(); if (!question) return;
  notify(""); pending(true); lastAnswer = null; $("answer-output").hidden = false; $("answer-status").textContent = "Working with the evidence…"; $("answer-time").textContent = ""; $("answer-text").textContent = "Retrieving evidence. Local generation, when enabled, can take a moment."; $("sources").replaceChildren(); $("sources-heading").hidden = true; $("download-answer").hidden = true; $("truncation").hidden = true;
  const started = performance.now();
  try {
    const data = await request("/ask", {question, query:$("query").value.trim() || null, evidence_limit:Number($("evidence-limit").value), retrieval_depth:20}); lastAnswer = data;
    $("answer-status").textContent = statusLabels[data.status] || data.status; $("answer-text").textContent = data.answer; $("answer-time").textContent = `${((performance.now()-started)/1000).toFixed(1)}s`;
    $("truncation").hidden = !data.context_truncated; $("sources-heading").hidden = !data.sources.length; $("sources-heading").textContent = data.status === "evidence_only" ? "Retrieved sources" : "Supporting sources";
    data.sources.forEach(item => {const link = sourceLink(item.source_html_url, null, "source-link"); link.append(el("strong", `[${item.citation_id}] ${item.publication_number} · ${item.buyer_country}`),el("span",item.title)); $("sources").append(link);}); $("download-answer").hidden = false;
  } catch(error) {notify(error.message); $("answer-output").hidden = true;}
  finally {pending(false);}
});
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => {if (!busy) showWorkspace(button.dataset.view);}));
document.querySelectorAll("[data-query]").forEach(button => button.addEventListener("click", () => {if (!busy) {$("query").value = button.dataset.query; $("query").focus();}}));
$("download-answer").addEventListener("click", () => {if (!lastAnswer) return; const url = URL.createObjectURL(new Blob([JSON.stringify(lastAnswer,null,2)], {type:"application/json"})); const a = el("a"); a.href = url; a.download = "tendergraph-answer.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);});
async function initialize() {
  restoreProfile(); showWorkspace(location.hash === "#explorer" ? "explorer" : "matches");
  const [health, config] = await Promise.allSettled([request("/health"),request("/config")]);
  $("connection-label").textContent = health.status === "fulfilled" ? "Database connected" : "Database unavailable"; $("connection-dot").className = "status-dot " + (health.status === "fulfilled" ? "ok" : "error");
  if (config.status === "fulfilled") {const mode = config.value.answer_mode; const labels = {evidence:"Evidence only",ollama:"Local AI",openai:"OpenAI · paid API"}; $("mode-pill").textContent = labels[mode] || mode; $("mode-label").textContent = config.value.generation_model || "No generation API calls"; if (mode === "evidence") {$("answer-help").textContent = "Evidence mode shows retrieved facts and sources. It does not generate an AI answer."; $("ask-button").textContent = "Show evidence →";}}
  else {$("mode-pill").textContent = "Mode unavailable"; $("mode-label").textContent = "Check server configuration";}
}
initialize();
