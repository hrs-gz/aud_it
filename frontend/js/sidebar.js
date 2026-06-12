/* Left sidebar: document list, page strip, rules list.
   Reads global `state`, calls global `Actions` (defined in app.js). */

const STATUS_DOT = {
  ready: { cls: "dot-ready", label: "ready" },
  ocr: { cls: "dot-busy", label: "running OCR" },
  detecting: { cls: "dot-busy", label: "detecting" },
  applying: { cls: "dot-busy", label: "applying" },
  verifying: { cls: "dot-busy", label: "verifying" },
  exporting: { cls: "dot-busy", label: "exporting" },
  error: { cls: "dot-error", label: "error" },
};

function docStageLabel(doc) {
  if (doc.status !== "ready") {
    return STATUS_DOT[doc.status] ? STATUS_DOT[doc.status].label : doc.status;
  }
  if (doc.exported_at) return "exported";
  if (doc.verified_at) return doc.verification_passed ? "verified" : "verify failed";
  if (doc.has_applied) return "applied";
  if (doc.detected_at) return "detected";
  return "pending";
}

function renderDocList() {
  const container = document.getElementById("doc-list");
  container.innerHTML = "";

  if (!state.documents.length) {
    container.innerHTML = '<p class="hint">No documents imported.</p>';
    document.getElementById("doc-count").textContent = "";
    return;
  }

  document.getElementById("doc-count").textContent =
    `${state.checkedDocIds.size}/${state.documents.length} selected`;

  for (const doc of state.documents) {
    const item = document.createElement("div");
    item.className = "doc-item" + (doc.id === state.currentDocId ? " active" : "");

    const dot = STATUS_DOT[doc.status] || STATUS_DOT.ready;
    const stage = docStageLabel(doc);
    const counts = doc.finding_counts || {};
    const unresolved = (counts.pending || 0) + (counts.needs_review || 0);

    item.innerHTML = `
      <input type="checkbox" class="doc-check" ${state.checkedDocIds.has(doc.id) ? "checked" : ""}>
      <div class="doc-main">
        <div class="doc-name" title="${doc.original_filename}">${doc.original_filename}</div>
        <div class="doc-meta">
          <span class="status-dot ${dot.cls}"></span>
          <span>${stage}</span>
          ${counts.total ? `<span class="badge-count" title="findings (unresolved)">${counts.total}${unresolved ? ` · ${unresolved} open` : ""}</span>` : ""}
          ${doc.is_scanned && !doc.has_ocr ? '<span class="badge-scan" title="Scanned — needs OCR">scan</span>' : ""}
        </div>
        ${doc.status_detail ? `<div class="doc-detail">${doc.status_detail}</div>` : ""}
        ${(doc.ocr_errors || []).map((e) => `<div class="doc-detail warn">OCR failed — p${e.page_num + 1}: ${e.reason}. Review page manually.</div>`).join("")}
      </div>
      <button class="btn tiny doc-delete" title="Remove document">✕</button>
    `;

    item.querySelector(".doc-check").addEventListener("click", (e) => {
      e.stopPropagation();
      Actions.toggleDocChecked(doc.id, e.target.checked);
    });
    item.querySelector(".doc-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      Actions.deleteDocument(doc.id);
    });
    item.addEventListener("click", () => Actions.openDocument(doc.id));

    container.appendChild(item);
  }
}

function renderPageStrip() {
  const container = document.getElementById("page-strip");
  const nameEl = document.getElementById("pages-doc-name");
  const doc = state.documents.find((d) => d.id === state.currentDocId);

  if (!doc) {
    container.innerHTML = '<p class="hint">Select a document.</p>';
    nameEl.textContent = "";
    return;
  }

  nameEl.textContent = doc.original_filename;
  container.innerHTML = "";

  for (const page of doc.pages) {
    const counts = page.finding_counts || {};
    const total = counts.total || 0;
    const unresolved = (counts.pending || 0) + (counts.needs_review || 0);

    const tile = document.createElement("div");
    tile.className =
      "page-tile" + (page.page_num === state.currentPage ? " active" : "");
    tile.innerHTML = `
      <img loading="lazy" src="${API.pageImageUrl(doc.id, page.page_num)}" alt="p${page.page_num + 1}">
      <div class="page-tile-label">
        P${page.page_num + 1}
        ${total ? `<span class="badge-count ${unresolved ? "open" : ""}">${total}</span>` : '<span class="badge-none">0</span>'}
      </div>
    `;
    tile.addEventListener("click", () => Actions.goToPage(page.page_num));
    container.appendChild(tile);
  }
}

function renderRulesList() {
  const container = document.getElementById("rules-list");
  container.innerHTML = "";

  if (!state.rules.length) {
    container.innerHTML = '<p class="hint">No rules yet. Select text in the viewer or click + New rule.</p>';
    return;
  }

  for (const rule of state.rules) {
    const item = document.createElement("div");
    item.className = "rule-item" + (rule.enabled ? "" : " disabled");
    item.innerHTML = `
      <input type="checkbox" ${rule.enabled ? "checked" : ""} title="Enabled">
      <div class="rule-main">
        <div class="rule-name">${rule.name}</div>
        <div class="rule-meta">${rule.entity_type} · ${rule.default_action === "approve" ? "auto-approve" : "review"}</div>
      </div>
    `;
    item.querySelector("input").addEventListener("click", (e) => {
      e.stopPropagation();
      Actions.toggleRule(rule.id, e.target.checked);
    });
    item.querySelector(".rule-main").addEventListener("click", () => openRuleEditor(rule));
    container.appendChild(item);
  }
}

function renderSidebar() {
  renderDocList();
  renderPageStrip();
  renderRulesList();
}
