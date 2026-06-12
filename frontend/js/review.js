/* Right pane: PII review (summary, Page View / PII View, finding cards, filters).
   Reads global `state`, calls global `Actions`. */

const STATUS_LABELS = {
  pending: "Pending",
  needs_review: "Needs review",
  approved: "Approved",
  applied: "Applied",
  ignored: "Ignored",
};

function entityLabel(entityType) {
  const entry = (state.recognizers || []).find((r) => r.entity_type === entityType);
  if (entry) return entry.label;
  if (entityType === "MANUAL") return "Manual box";
  if (entityType === "CUSTOM_SEARCH") return "Search match";
  return entityType.replace(/_/g, " ");
}

function docName(docId) {
  const doc = state.documents.find((d) => d.id === docId);
  return doc ? doc.original_filename : docId;
}

function filteredFindings() {
  const f = state.filters;
  return state.findings.filter((finding) => {
    if (f.entityType && finding.entity_type !== f.entityType) return false;
    if (f.status && finding.status !== f.status) return false;
    if (f.source && finding.source !== f.source) return false;
    if (f.minConfidence != null && finding.confidence < f.minConfidence) return false;
    return true;
  });
}

function renderSummaryChips(findings) {
  const container = document.getElementById("summary-chips");
  container.innerHTML = "";

  if (!findings.length) {
    container.innerHTML = '<span class="hint">No findings in scope.</span>';
    return;
  }

  const byType = {};
  for (const f of findings) {
    byType[f.entity_type] = (byType[f.entity_type] || 0) + 1;
  }
  const entries = Object.entries(byType).sort((a, b) => b[1] - a[1]);
  for (const [type, count] of entries) {
    const chip = document.createElement("button");
    chip.className = "chip" + (state.filters.entityType === type ? " active" : "");
    chip.textContent = `${entityLabel(type)} ${count}`;
    chip.addEventListener("click", () => {
      state.filters.entityType = state.filters.entityType === type ? "" : type;
      document.getElementById("filter-type").value = state.filters.entityType;
      renderReview();
    });
    container.appendChild(chip);
  }
}

function maskedOrRevealed(finding) {
  if (state.revealed[finding.id] !== undefined) return state.revealed[finding.id];
  return finding.masked_text;
}

function findingCard(finding) {
  const card = document.createElement("div");
  card.className =
    `finding-card status-${finding.status}` +
    (finding.id === state.activeFindingId ? " active" : "");
  card.dataset.findingId = finding.id;

  const revealed = state.revealed[finding.id] !== undefined;
  const valueText = maskedOrRevealed(finding) || "(area)";
  const isFinal = finding.status === "applied";

  card.innerHTML = `
    <div class="card-row">
      <input type="checkbox" class="card-check" ${state.selectedFindingIds.has(finding.id) ? "checked" : ""} ${isFinal ? "disabled" : ""}>
      <span class="card-type">${entityLabel(finding.entity_type)}</span>
      <span class="card-value" title="${revealed ? "revealed" : "masked"}">${valueText}</span>
      ${finding.text !== null || finding.masked_text ? `<button class="btn tiny card-reveal">${revealed ? "Hide" : "Reveal"}</button>` : ""}
    </div>
    <div class="card-row meta">
      <span>${Math.round(finding.confidence * 100)}%</span>
      <span title="${docName(finding.document_id)}">${docName(finding.document_id)}</span>
      <span>P${finding.page_num + 1}</span>
      <span class="status-chip chip-${finding.status}">${STATUS_LABELS[finding.status] || finding.status}</span>
      ${finding.source !== "auto" ? `<span class="source-tag">${finding.rule_name || finding.source}</span>` : ""}
    </div>
    <div class="card-row actions">
      ${isFinal ? "" : `
        <button class="btn tiny danger card-redact">${finding.status === "approved" ? "Unmark" : "Redact"}</button>
        <button class="btn tiny card-ignore">${finding.status === "ignored" ? "Restore" : "Ignore"}</button>
      `}
      <button class="btn tiny card-jump">Jump</button>
      ${finding.value_key && !isFinal ? '<button class="btn tiny card-redact-all">Redact all matching</button>' : ""}
      ${finding.value_key ? '<button class="btn tiny card-rule">Create rule</button>' : ""}
      ${finding.source === "manual" && !isFinal ? '<button class="btn tiny card-delete">Delete</button>' : ""}
    </div>
  `;

  const check = card.querySelector(".card-check");
  check.addEventListener("click", (e) => {
    e.stopPropagation();
    if (e.target.checked) state.selectedFindingIds.add(finding.id);
    else state.selectedFindingIds.delete(finding.id);
  });

  const revealBtn = card.querySelector(".card-reveal");
  if (revealBtn) {
    revealBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      Actions.toggleReveal(finding.id);
    });
  }

  const wire = (selector, handler) => {
    const el = card.querySelector(selector);
    if (el) el.addEventListener("click", (e) => { e.stopPropagation(); handler(); });
  };
  wire(".card-redact", () =>
    Actions.setFindingStatus(finding.id, finding.status === "approved" ? "pending" : "approved"));
  wire(".card-ignore", () =>
    Actions.setFindingStatus(finding.id, finding.status === "ignored" ? "pending" : "ignored"));
  wire(".card-jump", () => Actions.jumpToFinding(finding));
  wire(".card-redact-all", () => Actions.redactAllMatching(finding));
  wire(".card-rule", () => Actions.createRuleFromFinding(finding));
  wire(".card-delete", () => Actions.deleteFinding(finding.id));

  card.addEventListener("click", () => Actions.jumpToFinding(finding));
  return card;
}

function renderPageView(container, findings) {
  const byDoc = new Map();
  for (const f of findings) {
    if (!byDoc.has(f.document_id)) byDoc.set(f.document_id, new Map());
    const byPage = byDoc.get(f.document_id);
    if (!byPage.has(f.page_num)) byPage.set(f.page_num, []);
    byPage.get(f.page_num).push(f);
  }

  for (const [docId, byPage] of byDoc) {
    const docHead = document.createElement("div");
    docHead.className = "group-doc";
    docHead.textContent = docName(docId);
    container.appendChild(docHead);

    for (const pageNum of [...byPage.keys()].sort((a, b) => a - b)) {
      const pageFindings = byPage.get(pageNum);
      const typeCounts = {};
      for (const f of pageFindings) {
        typeCounts[f.entity_type] = (typeCounts[f.entity_type] || 0) + 1;
      }
      const summary = Object.entries(typeCounts)
        .map(([t, n]) => `${entityLabel(t)} ${n}`)
        .join(" · ");

      const groupKey = `page:${docId}:${pageNum}`;
      const expanded = state.expandedGroups.has(groupKey);

      const head = document.createElement("div");
      head.className = "group-page";
      head.innerHTML = `
        <button class="btn tiny group-toggle">${expanded ? "▾" : "▸"}</button>
        <span class="group-page-label">P${pageNum + 1}</span>
        <span class="group-page-summary">${summary}</span>
        <button class="btn tiny danger page-redact" title="Mark all on page for redaction">Redact page</button>
        <button class="btn tiny page-ignore" title="Ignore all on page">Ignore</button>
      `;
      head.querySelector(".group-page-label").addEventListener("click", () =>
        Actions.jumpToPage(docId, pageNum));
      head.querySelector(".group-toggle").addEventListener("click", () => {
        if (expanded) state.expandedGroups.delete(groupKey);
        else state.expandedGroups.add(groupKey);
        renderReview();
      });
      head.querySelector(".page-redact").addEventListener("click", () =>
        Actions.bulkPage(docId, pageNum, "approve"));
      head.querySelector(".page-ignore").addEventListener("click", () =>
        Actions.bulkPage(docId, pageNum, "ignore"));
      container.appendChild(head);

      if (expanded) {
        for (const f of pageFindings) container.appendChild(findingCard(f));
      }
    }
  }
}

function renderPiiView(container, findings) {
  const byType = new Map();
  for (const f of findings) {
    if (!byType.has(f.entity_type)) byType.set(f.entity_type, new Map());
    const byValue = byType.get(f.entity_type);
    const key = f.value_key || `#${f.id}`;
    if (!byValue.has(key)) byValue.set(key, []);
    byValue.get(key).push(f);
  }

  for (const [type, byValue] of byType) {
    const typeHead = document.createElement("div");
    typeHead.className = "group-doc";
    typeHead.textContent = entityLabel(type);
    container.appendChild(typeHead);

    for (const [key, group] of byValue) {
      const sample = group[0];
      const groupKey = `pii:${type}:${key}`;
      const expanded = state.expandedGroups.has(groupKey);
      const allFinal = group.every((f) => f.status === "applied");

      const head = document.createElement("div");
      head.className = "group-page";
      head.innerHTML = `
        <button class="btn tiny group-toggle">${expanded ? "▾" : "▸"}</button>
        <span class="group-page-label value">${maskedOrRevealed(sample) || "(area)"}</span>
        <span class="group-page-summary">× ${group.length}</span>
        ${allFinal ? '<span class="status-chip chip-applied">Applied</span>' : `
          <button class="btn tiny danger group-redact">Redact all</button>
          <button class="btn tiny group-ignore">Ignore all</button>
        `}
      `;
      head.querySelector(".group-toggle").addEventListener("click", () => {
        if (expanded) state.expandedGroups.delete(groupKey);
        else state.expandedGroups.add(groupKey);
        renderReview();
      });
      const redactBtn = head.querySelector(".group-redact");
      if (redactBtn) {
        redactBtn.addEventListener("click", () => Actions.redactAllMatching(sample));
      }
      const ignoreBtn = head.querySelector(".group-ignore");
      if (ignoreBtn) {
        ignoreBtn.addEventListener("click", () => Actions.ignoreAllMatching(sample));
      }
      container.appendChild(head);

      if (expanded) {
        for (const f of group) container.appendChild(findingCard(f));
      }
    }
  }
}

function renderReview() {
  const findings = filteredFindings();
  renderSummaryChips(findings);

  const container = document.getElementById("review-body");
  container.innerHTML = "";

  if (!state.findings.length) {
    container.innerHTML =
      '<p class="hint">No findings yet. Select documents and run Detect.</p>';
    return;
  }
  if (!findings.length) {
    container.innerHTML = '<p class="hint">No findings match the current filters.</p>';
    return;
  }

  if (state.viewMode === "page") renderPageView(container, findings);
  else renderPiiView(container, findings);
}
