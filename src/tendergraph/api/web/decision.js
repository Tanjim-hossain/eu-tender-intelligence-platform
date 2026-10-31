"use strict";
(() => {
  const ACCOUNT_KEY = "tendergraph.productAccountId.v1";
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

  const readinessLabel = (value) => ({
    ready_for_bid_review: "Ready for bid review",
    hold_for_evidence: "Hold for evidence",
    critical_attention: "Critical attention",
    deadline_closed: "Deadline closed",
    user_no_bid: "User marked no-bid"
  }[value] || String(value || "Review"));

  const statusLabel = (value) => ({
    unreviewed: "Unreviewed",
    verified: "Verified",
    needs_evidence: "Needs evidence",
    not_applicable: "Not applicable"
  }[value] || value);

  const sourceLabel = (item) => {
    const parts = [];
    if (item.source_kind === "procurement_document") parts.push("Procurement document");
    else parts.push("TED notice");
    if (item.document_id) parts.push(item.document_id);
    if (item.page_number != null) parts.push(`Page ${item.page_number}`);
    if (item.section_title) parts.push(`Section: ${item.section_title}`);
    if (item.chunk_id) parts.push(`Chunk ${item.chunk_id}`);
    return parts.join(" · ");
  };

  const sectionTitle = (title, count = null) => {
    const heading = make("h4", null, "decision-section-title");
    heading.append(document.createTextNode(title));
    if (count != null) heading.append(make("span", String(count), "decision-count"));
    return heading;
  };

  const accountId = () => localStorage.getItem(ACCOUNT_KEY);

  const request = async (path, options = {}) => {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})}
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Decision dossier request failed (${response.status})`);
    }
    return response.json();
  };

  const riskList = (items) => {
    const list = make("div", null, "decision-risk-list");
    items.forEach((item) => {
      const row = make("div", null, `decision-risk risk-${item.severity}`);
      const top = make("div", null, "decision-row-top");
      top.append(
        make("strong", item.message),
        make("span", String(item.severity).toUpperCase(), `decision-pill risk-${item.severity}`)
      );
      row.append(top, make("small", item.source_kind.replaceAll("_", " "), "decision-source"));
      list.append(row);
    });
    return list;
  };

  const reviewPayload = (panel, data) => ({
    items: data.checklist.map((item) => {
      const row = panel.querySelector(`[data-decision-key="${CSS.escape(item.key)}"]`);
      const select = row?.querySelector("select");
      const note = row?.querySelector("input");
      return {
        key: item.key,
        status: select?.value || item.manual_status || "unreviewed",
        note: String(note?.value || "").trim().slice(0, 1000)
      };
    }),
    reviewer_note: String(panel.querySelector(".decision-reviewer-note")?.value || "").trim().slice(0, 5000)
  });

  const renderChecklist = (panel, data, onSave) => {
    const list = make("div", null, "decision-checklist");
    data.checklist.forEach((item) => {
      const row = make("div", null, `decision-checklist-item ${item.hard_gate ? "hard-gate" : ""}`);
      row.dataset.decisionKey = item.key;
      const top = make("div", null, "decision-row-top");
      const identity = make("div", null, "decision-item-identity");
      identity.append(
        make("strong", item.label),
        make("span", item.category, "decision-category")
      );
      if (item.hard_gate) identity.append(make("span", "Potential hard gate", "decision-pill hard-gate"));
      identity.append(make("span", item.evidence_strength, `decision-pill ${item.evidence_strength}`));
      top.append(identity);

      const source = make("div", sourceLabel(item), "decision-source");
      const evidence = make("p", item.evidence, "decision-evidence");
      row.append(top, source, evidence);

      if (item.source_url) {
        const link = make("a", "Open evidence source ↗", "decision-source-link");
        link.href = item.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        row.append(link);
      }

      const review = make("div", null, "decision-review-controls");
      const selectLabel = make("label");
      selectLabel.append(make("span", "Evidence review"));
      const select = make("select");
      [
        ["unreviewed", "Unreviewed"],
        ["verified", "Verified"],
        ["needs_evidence", "Needs evidence"],
        ["not_applicable", "Not applicable"]
      ].forEach(([value, label]) => {
        const option = make("option", label);
        option.value = value;
        option.selected = value === item.manual_status;
        select.append(option);
      });
      selectLabel.append(select);

      const noteLabel = make("label", null, "decision-item-note");
      noteLabel.append(make("span", "Review note"));
      const note = make("input");
      note.type = "text";
      note.maxLength = 1000;
      note.placeholder = "Evidence location, owner, or follow-up";
      note.value = item.manual_note || "";
      noteLabel.append(note);
      review.append(selectLabel, noteLabel);
      row.append(review);
      list.append(row);
    });

    if (!data.checklist.length) {
      list.append(make(
        "p",
        "No supported requirement signals were detected. This does not prove that the tender has no mandatory requirements; verify the official package.",
        "decision-empty"
      ));
    }

    panel.append(list);

    const reviewer = make("label", null, "decision-reviewer-field");
    reviewer.append(make("span", "Overall reviewer note"));
    const reviewerNote = make("textarea", null, "decision-reviewer-note");
    reviewerNote.rows = 3;
    reviewerNote.maxLength = 5000;
    reviewerNote.placeholder = "Commercial rationale, internal owner, missing evidence, or final decision context";
    reviewerNote.value = data.reviewer_note || "";
    reviewer.append(reviewerNote);
    panel.append(reviewer);

    const save = make("button", "Save evidence review", "decision-save secondary");
    save.type = "button";
    save.addEventListener("click", () => onSave(save));
    panel.append(save);
  };

  const render = (panel, data, saveReview) => {
    panel.replaceChildren();

    const header = make("div", null, "decision-header");
    const heading = make("div");
    heading.append(
      make("span", "BID / NO-BID DECISION DOSSIER", "eyebrow"),
      make("h3", readinessLabel(data.review_readiness))
    );
    header.append(
      heading,
      make(
        "span",
        readinessLabel(data.review_readiness),
        `decision-status status-${data.review_readiness}`
      )
    );
    panel.append(header, make("p", data.review_message, "decision-message"));

    const meta = make("div", null, "decision-meta");
    meta.append(
      make("span", `Company fit: ${data.strategic_fit}`),
      make("span", `Stored fit score: ${data.match_score == null ? "—" : Math.round(data.match_score) + "%"}`),
      make("span", `Deadline: ${data.deadline_readiness}${data.days_to_deadline == null ? "" : ` · ${data.days_to_deadline} day(s)`}`),
      make("span", `Notice risk: ${data.notice_risk_level}`),
      make("span", `Document coverage: ${data.document_coverage}`),
      make("span", `Pipeline: ${String(data.pipeline_stage).replaceAll("_", " ")}`)
    );
    panel.append(meta);

    if (data.strategic_fit_reasons.length) {
      panel.append(sectionTitle("Strategic fit"));
      const reasons = make("ul", null, "decision-actions");
      data.strategic_fit_reasons.forEach((item) => reasons.append(make("li", item)));
      panel.append(reasons);
    }

    const summary = data.evidence_summary;
    const evidenceSummary = make("div", null, "decision-summary-grid");
    [
      ["Requirements", summary.requirement_count],
      ["Hard gates", summary.hard_gate_count],
      ["Hard gates verified", summary.hard_gates_verified],
      ["Verified", summary.verified_count],
      ["Needs evidence", summary.needs_evidence_count],
      ["Unreviewed", summary.unreviewed_count]
    ].forEach(([label, value]) => {
      const card = make("div", null, "decision-summary-card");
      card.append(make("strong", String(value)), make("span", label));
      evidenceSummary.append(card);
    });
    panel.append(evidenceSummary);

    panel.append(sectionTitle("Evidence checklist", data.checklist.length));
    renderChecklist(panel, data, saveReview);

    if (data.risks.length) {
      panel.append(sectionTitle("Consolidated risks", data.risks.length));
      panel.append(riskList(data.risks));
    }

    panel.append(sectionTitle("Next actions", data.next_actions.length));
    const actions = make("ol", null, "decision-actions");
    data.next_actions.forEach((action) => actions.append(make("li", action)));
    panel.append(actions);

    if (data.pipeline_note) {
      panel.append(sectionTitle("Pipeline decision note"));
      panel.append(make("p", data.pipeline_note, "decision-pipeline-note"));
    }

    panel.append(make("p", data.disclaimer, "decision-disclaimer"));
  };

  const load = async (button, panel, publication) => {
    const id = accountId();
    if (!id) {
      panel.hidden = false;
      panel.replaceChildren(make("p", "Product account is still initializing. Try again after the workspace finishes loading.", "decision-error"));
      return;
    }

    button.disabled = true;
    button.textContent = "Building dossier…";
    panel.hidden = false;
    panel.replaceChildren(make("p", "Consolidating company fit, notice requirements, document evidence, provenance, deadline readiness, and saved pipeline state…", "decision-loading"));

    let currentData = null;
    const path = `/decisions/accounts/${encodeURIComponent(id)}/opportunities/${encodeURIComponent(publication)}`;

    const saveReview = async (saveButton) => {
      if (!currentData) return;
      saveButton.disabled = true;
      saveButton.textContent = "Saving review…";
      try {
        const updated = await request(`${path}/review`, {
          method: "PUT",
          body: JSON.stringify(reviewPayload(panel, currentData))
        });
        currentData = updated;
        render(panel, currentData, saveReview);
      } catch (error) {
        saveButton.disabled = false;
        saveButton.textContent = "Retry save";
        const message = make("p", error instanceof Error ? error.message : "Decision review could not be saved.", "decision-error");
        panel.prepend(message);
      }
    };

    try {
      currentData = await request(path);
      render(panel, currentData, saveReview);
      button.textContent = "Refresh decision dossier";
    } catch (error) {
      panel.replaceChildren(
        make("p", error instanceof Error ? error.message : "Decision dossier unavailable.", "decision-error"),
        make("p", "The saved opportunity is unchanged. Review the official TED notice and procurement documents manually.", "decision-disclaimer")
      );
      button.textContent = "Retry decision dossier";
    } finally {
      button.disabled = false;
    }
  };

  const enhance = () => {
    container.querySelectorAll(".saved-card").forEach((card) => {
      if (card.querySelector(".decision-dossier-toggle")) return;
      const publication = publicationNumber(card);
      if (!publication) return;
      const actions = card.querySelector(".saved-card-actions");
      if (!actions) return;

      const button = make("button", "Open decision dossier", "decision-dossier-toggle secondary");
      button.type = "button";
      const panel = make("section", null, "decision-panel");
      panel.hidden = true;
      panel.setAttribute("aria-label", `Bid/no-bid decision dossier for ${publication}`);
      button.addEventListener("click", () => load(button, panel, publication));

      actions.prepend(button);
      card.append(panel);
    });
  };

  new MutationObserver(enhance).observe(container, {childList: true, subtree: true});
  enhance();
})();
