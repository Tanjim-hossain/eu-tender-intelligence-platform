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

  const strengthLabel = (value) => value === "explicit" ? "Explicit requirement signal" : "Mentioned in source text";

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
      if (item.document_id) top.append(make("span", item.document_id, "signal-pill mentioned"));
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
    heading.append(make("span", "NOTICE QUALIFICATION REVIEW", "eyebrow"), make("h3", statusLabel(data.review_status)));
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

  const documentStatusLabel = (value) => ({
    discovered: "Discovered",
    restricted: "Restricted",
    extracted: "Text extracted",
    fetched: "Fetched",
    unsupported: "Needs manual review",
    access_denied: "Access denied",
    failed: "Fetch failed"
  }[value] || value);

  const renderPackage = (panel, packageData, intelligence) => {
    panel.replaceChildren();
    const header = make("div", null, "qualification-header");
    const heading = make("div");
    heading.append(make("span", "FULL TENDER PACKAGE", "eyebrow"), make("h3", "Procurement document intelligence"));
    header.append(heading, make("span", String(packageData.package_status).replaceAll("_", " "), "qualification-status risk-unknown"));
    panel.append(header);

    const meta = make("div", null, "qualification-meta");
    meta.append(
      make("span", `${packageData.documents.length} official document reference(s)`),
      make("span", `${packageData.extracted_document_count} text-extracted`),
      make("span", `${packageData.restricted_document_count} restricted`),
      make("span", `Package coverage: ${intelligence.coverage}`)
    );
    panel.append(meta);

    panel.append(sectionTitle("Official procurement document links", packageData.documents.length));
    if (!packageData.documents.length) {
      panel.append(make("p", "The official TED XML did not expose procurement-document references for this notice.", "qualification-empty"));
    } else {
      const list = make("div", null, "qualification-list");
      packageData.documents.forEach((item) => {
        const row = make("div", null, "qualification-item");
        const top = make("div", null, "qualification-item-top");
        top.append(make("strong", item.document_id));
        top.append(make("span", documentStatusLabel(item.status), `signal-pill ${item.status === "extracted" ? "explicit" : "mentioned"}`));
        if (item.restricted) top.append(make("span", "Controlled access", "signal-pill hard-gate"));
        const link = make("a", "Open buyer document ↗", "package-link");
        link.href = item.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        row.append(top, link);
        if (item.content_type) row.append(make("p", `${item.content_type}${item.byte_count != null ? ` · ${item.byte_count.toLocaleString()} bytes` : ""}`, "qualification-evidence"));
        if (item.error) row.append(make("p", item.error, "qualification-error"));
        list.append(row);
      });
      panel.append(list);
    }

    panel.append(sectionTitle("Requirements found in fetched documents", intelligence.requirements.length));
    if (intelligence.requirements.length) {
      panel.append(evidenceList(intelligence.requirements, "requirement"));
    } else {
      panel.append(make("p", "No supported requirement signals were found in documents TenderGraph could convert to text.", "qualification-empty"));
    }

    if (intelligence.risks.length) {
      panel.append(sectionTitle("Package review risks", intelligence.risks.length));
      panel.append(riskList(intelligence.risks));
    }

    panel.append(sectionTitle("Next package actions", intelligence.next_actions.length));
    const actions = make("ol", null, "qualification-actions");
    intelligence.next_actions.forEach((action) => actions.append(make("li", action)));
    panel.append(actions, make("p", intelligence.disclaimer, "qualification-disclaimer"));
  };

  const load = async (button, panel, publication) => {
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
      button.textContent = "Refresh notice review";
    } catch (error) {
      panel.replaceChildren(
        make("p", error instanceof Error ? error.message : "Qualification review unavailable.", "qualification-error"),
        make("p", "Your saved opportunity is unchanged. Use the official TED notice for manual verification.", "qualification-disclaimer")
      );
      button.textContent = "Retry notice review";
    } finally {
      button.disabled = false;
    }
  };

  const loadPackage = async (button, panel, publication) => {
    button.disabled = true;
    button.textContent = "Ingesting official package…";
    panel.hidden = false;
    panel.replaceChildren(make("p", "Reading the official TED XML, fetching unrestricted document URLs safely, and extracting locally supported text…", "qualification-loading"));
    try {
      const ingestResponse = await fetch(`/documents/${encodeURIComponent(publication)}/ingest`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({fetch_documents: true, force: false})
      });
      if (!ingestResponse.ok) {
        const payload = await ingestResponse.json().catch(() => ({}));
        throw new Error(payload.detail || `Document ingestion failed (${ingestResponse.status})`);
      }
      const packageData = await ingestResponse.json();
      const intelligenceResponse = await fetch(`/documents/${encodeURIComponent(publication)}/intelligence`);
      if (!intelligenceResponse.ok) {
        const payload = await intelligenceResponse.json().catch(() => ({}));
        throw new Error(payload.detail || `Package intelligence failed (${intelligenceResponse.status})`);
      }
      renderPackage(panel, packageData, await intelligenceResponse.json());
      button.textContent = "Refresh tender package";
    } catch (error) {
      panel.replaceChildren(
        make("p", error instanceof Error ? error.message : "Tender package ingestion unavailable.", "qualification-error"),
        make("p", "TenderGraph never bypasses registration, authentication, or restricted-document controls. Open the official buyer link manually when automated access is unavailable.", "qualification-disclaimer")
      );
      button.textContent = "Retry tender package";
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

      const noticeButton = make("button", "Review notice requirements", "qualification-toggle secondary");
      noticeButton.type = "button";
      const noticePanel = make("section", null, "qualification-panel");
      noticePanel.hidden = true;
      noticePanel.setAttribute("aria-label", `Notice qualification review for ${publication}`);
      noticeButton.addEventListener("click", () => load(noticeButton, noticePanel, publication));

      const packageButton = make("button", "Ingest tender package", "package-toggle secondary");
      packageButton.type = "button";
      const packagePanel = make("section", null, "qualification-panel package-panel");
      packagePanel.hidden = true;
      packagePanel.setAttribute("aria-label", `Procurement document package for ${publication}`);
      packageButton.addEventListener("click", () => loadPackage(packageButton, packagePanel, publication));

      actions.prepend(packageButton);
      actions.prepend(noticeButton);
      card.append(noticePanel, packagePanel);
    });
  };

  new MutationObserver(enhance).observe(container, {childList: true, subtree: true});
  enhance();
})();
