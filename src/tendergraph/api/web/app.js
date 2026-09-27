"use strict";
const $ = (id) => document.getElementById(id);
let lastAnswer = null;
let busy = false;
const statusLabels = {answered: "Answer with citations", evidence_only: "Retrieved evidence", no_results: "No notices found", insufficient_evidence: "Insufficient evidence"};
function el(tag, text, className) {const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node;}
function sourceURL(raw) {try {const url = new URL(raw); return url.protocol === "https:" && url.hostname === "ted.europa.eu" ? url.href : null;} catch {return null;}}
function sourceLink(raw, text, className) {const url = sourceURL(raw); const node = el(url ? "a" : "span", text, className); if (url) {node.href = url; node.target = "_blank"; node.rel = "noopener noreferrer";} return node;}
function notify(message) {$("notice").textContent = message; $("notice").hidden = !message;}
function pending(value) {busy = value; $("search-button").disabled = value; $("ask-button").disabled = value; $("search-form").setAttribute("aria-busy", String(value)); $("ask-form").setAttribute("aria-busy", String(value));}
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
function renderResults(data) {
  $("results").replaceChildren(); $("result-count").textContent = data.count;
  if (!data.count) {const empty = el("div", null, "empty-state"); empty.append(el("h3", "No matching notices found."), el("p", "Try a broader topic or a different service name.")); $("results").append(empty); return;}
  data.results.forEach((item, index) => {
    const card = el("article", null, "tender-card"); const top = el("div", null, "card-top"); top.append(el("span", String(index + 1).padStart(2,"0"), "rank"), el("span", item.buyer_country), el("span", "·"), el("span", item.publication_number));
    const fields = el("dl", null, "card-fields");
    const value = item.estimated_value == null ? "Not stated" : `${item.estimated_value} ${item.estimated_value_currency || ""}`.trim();
    [["BUYER", item.buyer_name || "Not stated"], ["DEADLINE", displayDate(item.earliest_deadline)], ["ESTIMATED VALUE", value], ["PUBLISHED", displayDate(item.publication_date)]].forEach(([label, text]) => {const group = el("div"); group.append(el("dt",label),el("dd",text)); fields.append(group);});
    const bottom = el("div", null, "card-bottom"); bottom.append(sourceLink(item.source_html_url, "Open TED notice ↗"), el("span", "Search match · verify relevance"));
    card.append(top, el("h3", item.title, "card-title"), fields, bottom); $("results").append(card);
  });
}
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
document.querySelectorAll("[data-query]").forEach(button => button.addEventListener("click", () => {if (!busy) {$("query").value = button.dataset.query; $("query").focus();}}));
$("download-answer").addEventListener("click", () => {if (!lastAnswer) return; const url = URL.createObjectURL(new Blob([JSON.stringify(lastAnswer,null,2)], {type:"application/json"})); const a = el("a"); a.href = url; a.download = "tendergraph-answer.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);});
async function initialize() {
  const [health, config] = await Promise.allSettled([request("/health"),request("/config")]);
  $("connection-label").textContent = health.status === "fulfilled" ? "Database connected" : "Database unavailable"; $("connection-dot").className = "status-dot " + (health.status === "fulfilled" ? "ok" : "error");
  if (config.status === "fulfilled") {const mode = config.value.answer_mode; const labels = {evidence:"Evidence only",ollama:"Local AI",openai:"OpenAI · paid API"}; $("mode-pill").textContent = labels[mode] || mode; $("mode-label").textContent = config.value.generation_model || "No generation API calls"; if (mode === "evidence") {$("answer-help").textContent = "Evidence mode shows retrieved facts and sources. It does not generate an AI answer."; $("ask-button").textContent = "Show evidence →";}}
  else {$("mode-pill").textContent = "Mode unavailable"; $("mode-label").textContent = "Check server configuration";}
}
initialize();
