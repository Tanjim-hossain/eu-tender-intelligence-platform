"use strict";
(() => {
  const container = document.getElementById("saved-results");
  if (!container) return;

  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };

  const publicationNumber = (card) => {
    const spans = card.querySelectorAll(".saved-meta span");
    const value = spans.length ? spans[spans.length - 1].textContent : "";
    return String(value || "").trim();
  };

  const statusLabel = (value) => ({
    no_flags: "No automated flags",
    attention: "Needs review",
    critical_attention: "Critical attention",
    insufficient_evidence: "Insufficient indexed evidence"
  }[value] || "Review available");

  const strengthLabel = (value) => value === "explicit" ? "Explicit requirement signal" : "Mentioned in notice text";

  const sectionTitle = (title, count) => {
    const heading = make("h4", null, "qualification-section-title");
    heading.append(document.createTextNode(title), make("span", String(count), "qualification-count"));
    return heading;
  };

  const evidenceList = (items, kind) => {
    const list = make("div", null, "qualification-list");
    items.forEach((item) => {
      const row = make("div", null, "qualification-item");
      const top = make("div", null, "qualification-item-top");
      top.append(make("strong", item.label));
      if (kind === "requirement") {
        top.append(make("span", strengthLabel(item.evidence_strength), `signal-pill ${item.evidence_strength}`));
        if (item.hard_gate) top.append(make("span", "Potential hard gate", "signal-pill hard-gate"));
      }
      row.append(top, make("p", item.evidence, "qualification-evidence"));
      list.append(row);
    });
    return list;
  };

  const riskList = (items) => {
    const list = make("div", null, "qualification-list");
    items.forEach((item) => {
      const row = make("div", null, `qualification-risk risk-${item.severity}`);
      const top = make("div", null, "qualification-item-top");
      top.append(make("strong", item.message), make("span", item.severity, `risk-pill risk-${item.severity}`));
      row.append(top);
      if (item.evidence) row.append(make("p", item.evidence, "qualification-evidence"));
      list.append(row);
    });
    return list;
  };

  const render = (panel, data) => {
    panel.replaceChildren();
    const header = make("div", null, "qualification-header");
    const heading = make("div");
    heading.append(make("span", "QUALIFICATION REVIEW", "eyebrow"), make("h3", statusLabel(data.review_status)));
    header.append(
      heading,
      make("span", `${String(data.risk_level || "unknown").toUpperCase()} RISK`, `qualification-status risk-${data.risk_level || "unknown"}`)
    );
    panel.append(header);

    const meta = make("div", null, "qualification-meta");
    meta.append(
      make("span", `Indexed evidence: ${data.evidence_coverage}`),
      make("span", `${data.requirements.length} requirement signal(s)`),
      make("span", `${data.document_signals.length} document signal(s)`)
    );
    panel.append(meta);

    if (data.requirements.length) {
      panel.append(sectionTitle("Requirements & eligibility signals", data.requirements.length));
      panel.append(evidenceList(data.requirements, "requirement"));
    } else {
      panel.append(sectionTitle("Requirements & eligibility signals", 0));
      panel.append(make("p", "No supported requirement phrases were found in the indexed description or lot text. Check the official procurement documents before deciding eligibility.", "qualification-empty"));
    }

    if (data.document_signals.length) {
      panel.append(sectionTitle("Referenced evidence / documents", data.document_signals.length));
      panel.append(evidenceList(data.document_signals, "document"));
    }

    if (data.risks.length) {
      panel.append(sectionTitle("Decision risks", data.risks.length));
      panel.append(riskList(data.risks));
    }

    panel.append(sectionTitle("Next review actions", data.next_actions.length));
    const actions = make("ol", null, "qualification-actions");
    data.next_actions.forEach((action) => actions.append(make("li", action)));
    panel.append(actions, make("p", data.disclaimer, "qualification-disclaimer"));
  };

  const load = async (card, button, panel, publication) => {
    button.disabled = true;
    button.textContent = "Reviewing indexed notice…";
    panel.hidden = false;
    panel.replaceChildren(make("p", "Extracting evidence-grounded qualification signals…", "qualification-loading"));
    try {
      const response = await fetch(`/qualification/${encodeURIComponent(publication)}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Qualification request failed (${response.status})`);
      }
      render(panel, await response.json());
      button.textContent = "Refresh requirements review";
    } catch (error) {
      panel.replaceChildren(
        make("p", error instanceof Error ? error.message : "Qualification review unavailable.", "qualification-error"),
        make("p", "Your saved opportunity is unchanged. Use the official TED notice for manual verification.", "qualification-disclaimer")
      );
      button.textContent = "Retry requirements review";
    } finally {
      button.disabled = false;
    }
  };

  const enhance = () => {
    container.querySelectorAll(".saved-card").forEach((card) => {
      if (card.querySelector(".qualification-toggle")) return;
      const publication = publicationNumber(card);
      if (!publication) return;
      const actions = card.querySelector(".saved-card-actions");
      if (!actions) return;

      const button = make("button", "Review requirements", "qualification-toggle secondary");
      button.type = "button";
      const panel = make("section", null, "qualification-panel");
      panel.hidden = true;
      panel.setAttribute("aria-label", `Qualification review for ${publication}`);
      button.addEventListener("click", () => load(card, button, panel, publication));
      actions.prepend(button);
      card.append(panel);
    });
  };

  new MutationObserver(enhance).observe(container, {childList: true, subtree: true});
  enhance();
})();
