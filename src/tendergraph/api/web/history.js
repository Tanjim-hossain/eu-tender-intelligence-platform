"use strict";
(() => {
  const container = document.getElementById("saved-results");
  if (!container) return;
  const make = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const safeTed = raw => {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" && url.hostname === "ted.europa.eu" ? url.href : null;
    } catch { return null; }
  };
  const money = value => Number.isFinite(Number(value)) ? new Intl.NumberFormat("en", {maximumFractionDigits:0}).format(Number(value)) : "Not stated";
  const render = (panel, data) => {
    panel.replaceChildren(
      make("h3", "Historical buyer activity"),
      make("p", `${data.buyer_name || "Unknown buyer"} · ${data.buyer_country}`, "decision-source"),
      make("p", `${data.notice_count} indexed earlier notices · ${data.result_notice_count} result notices · ${data.window_start} to before ${data.window_end_exclusive}`, "decision-message")
    );
    data.values.forEach(v => panel.append(make("p", `Observed median estimated value: ${v.currency} ${money(v.median_estimated_value)} (${v.known_values} notices)`, "decision-source")));
    if (!data.notices.length) panel.append(make("p", "No matching earlier notices in the loaded window. This does not establish that the buyer has no procurement history.", "decision-empty"));
    data.notices.forEach(item => {
      const row = make("article", null, "decision-checklist-item");
      row.append(make("strong", item.title), make("p", `${item.publication_date} · ${item.notice_type} · ${item.publication_number}`, "decision-source"));
      if (item.estimated_value != null) row.append(make("p", `Estimated value: ${item.currency || ""} ${money(item.estimated_value)}`, "decision-source"));
      if (item.suppliers.length) {
        const names = [...new Set(item.suppliers.map(s => s.name))];
        row.append(make("p", `Historical contract-linked suppliers: ${names.join("; ")}`, "decision-evidence"));
      } else if (item.notice_type.startsWith("can-")) {
        row.append(make("p", item.award_evidence_indexed ? "No supported public organization evidence extracted." : "Award XML evidence has not been indexed.", "decision-source"));
      }
      const url = safeTed(item.source_url);
      if (url) {
        const link = make("a", "Official TED source ↗", "decision-source-link");
        link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
        row.append(link);
      }
      panel.append(row);
    });
    panel.append(make("p", data.disclaimer, "decision-disclaimer"));
  };
  const enhance = () => container.querySelectorAll(".saved-card").forEach(card => {
    if (card.querySelector(".history-toggle")) return;
    const spans = card.querySelectorAll(".saved-meta span");
    const publication = spans[spans.length - 1]?.textContent?.trim();
    const actions = card.querySelector(".saved-card-actions");
    if (!publication || !actions) return;
    const button = make("button", "Buyer history", "secondary history-toggle");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    const panel = make("section", null, "decision-panel history-panel");
    panel.hidden = true;
    panel.setAttribute("aria-label", "Historical procurement");
    button.addEventListener("click", async () => {
      if (!panel.hidden) { panel.hidden = true; button.setAttribute("aria-expanded", "false"); return; }
      panel.hidden = false; button.setAttribute("aria-expanded", "true");
      button.disabled = true;
      panel.replaceChildren(make("p", "Loading indexed history…", "decision-loading"));
      try {
        const response = await fetch(`/history/${encodeURIComponent(publication)}`, {credentials:"same-origin"});
        if (!response.ok) throw new Error(`History unavailable (${response.status})`);
        render(panel, await response.json());
      } catch (error) {
        panel.replaceChildren(make("p", error.message, "decision-error"));
      } finally { button.disabled = false; }
    });
    actions.prepend(button); card.append(panel);
  });
  new MutationObserver(enhance).observe(container, {childList:true, subtree:true});
  enhance();
})();
