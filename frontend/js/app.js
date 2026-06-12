/* App state, actions, and wiring for the three-panel review workflow. */

const state = {
  documents: [],
  checkedDocIds: new Set(),
  currentDocId: null,
  currentPage: 0,
  findings: [],
  revealed: {},
  selectedFindingIds: new Set(),
  activeFindingId: null,
  expandedGroups: new Set(),
  viewMode: "page",
  filters: { entityType: "", status: "", source: "", minConfidence: null },
  showRedacted: false,
  zoom: 1,
  rules: [],
  recognizers: [],
  pollTimer: null,
};

const canvas = new RedactionCanvas(
  document.getElementById("page-canvas"),
  document.getElementById("overlay-canvas"),
  document.getElementById("canvas-container")
);

const BUSY_STATUSES = new Set(["ocr", "detecting", "applying", "verifying", "exporting"]);

function currentDoc() {
  return state.documents.find((d) => d.id === state.currentDocId) || null;
}

function groupKeysFor(finding) {
  return [
    `page:${finding.document_id}:${finding.page_num}`,
    `pii:${finding.entity_type}:${finding.value_key || `#${finding.id}`}`,
  ];
}

// ---------------------------------------------------------------------------
// Data loading

async function refreshDocuments() {
  const result = await API.listDocuments();
  state.documents = result.documents;

  const ids = new Set(state.documents.map((d) => d.id));
  state.checkedDocIds = new Set([...state.checkedDocIds].filter((id) => ids.has(id)));
  if (state.currentDocId && !ids.has(state.currentDocId)) {
    state.currentDocId = null;
  }
  if (!state.currentDocId && state.documents.length) {
    state.currentDocId = state.documents[0].id;
    state.currentPage = 0;
  }

  renderGlobalStatus();
  renderSidebar();
  updateViewerToolbar();
  schedulePollingIfBusy();
}

async function refreshFindings() {
  const docIds = Actions.scopeDocIds();
  if (!docIds.length) {
    state.findings = [];
  } else {
    const result = await API.getFindings({ documentIds: docIds });
    state.findings = result.findings;
  }
  const known = new Set(state.findings.map((f) => f.id));
  state.selectedFindingIds = new Set([...state.selectedFindingIds].filter((id) => known.has(id)));
  renderReview();
  updateCanvasFindings();
}

async function refreshAll() {
  await refreshDocuments();
  await refreshFindings();
  await loadPage();
}

function schedulePollingIfBusy() {
  const busy = state.documents.some((d) => BUSY_STATUSES.has(d.status));
  if (busy && !state.pollTimer) {
    state.pollTimer = setTimeout(async () => {
      state.pollTimer = null;
      const wasBusy = state.documents.some((d) => BUSY_STATUSES.has(d.status));
      await refreshDocuments();
      const stillBusy = state.documents.some((d) => BUSY_STATUSES.has(d.status));
      if (wasBusy && !stillBusy) {
        await refreshFindings();
        await loadPage();
      }
    }, 1200);
  }
}

function renderGlobalStatus() {
  const el = document.getElementById("global-status");
  const counts = {};
  for (const doc of state.documents) {
    if (BUSY_STATUSES.has(doc.status)) counts[doc.status] = (counts[doc.status] || 0) + 1;
  }
  const parts = Object.entries(counts).map(([status, n]) => {
    const labels = {
      ocr: "Running OCR",
      detecting: "Detecting",
      applying: "Applying redactions",
      verifying: "Verifying",
      exporting: "Exporting",
    };
    return `${labels[status] || status} ${n} doc(s)`;
  });
  const errors = state.documents.filter((d) => d.status === "error").length;
  if (errors) parts.push(`<span class="fail">${errors} error(s)</span>`);
  el.innerHTML = parts.length
    ? `<span class="spinner"></span> ${parts.join(" · ")}`
    : "";
}

// ---------------------------------------------------------------------------
// Viewer

async function loadPage() {
  const doc = currentDoc();
  const emptyEl = document.getElementById("viewer-empty");
  const container = document.getElementById("canvas-container");

  if (!doc) {
    emptyEl.classList.remove("hidden");
    container.classList.add("hidden");
    return;
  }
  emptyEl.classList.add("hidden");
  container.classList.remove("hidden");

  state.currentPage = Math.min(state.currentPage, doc.page_count - 1);
  document.getElementById("page-indicator").textContent =
    `${state.currentPage + 1} / ${doc.page_count}`;

  canvas.setRenderScale(doc.render_scale);
  canvas.zoom = state.zoom;

  const version = state.showRedacted && doc.has_applied ? "redacted" : "original";
  canvas.setShowOverlays(version === "original");

  try {
    await canvas.loadPageImage(API.pageImageUrl(doc.id, state.currentPage, version));
  } catch (_) {
    // redacted render may not exist yet
    if (version === "redacted") {
      state.showRedacted = false;
      updateViewerToolbar();
      await canvas.loadPageImage(API.pageImageUrl(doc.id, state.currentPage, "original"));
    }
  }

  updateCanvasFindings();
  loadWordsForPage();
  renderPageStrip();
}

function updateCanvasFindings() {
  const doc = currentDoc();
  if (!doc) return;
  const pageFindings = state.findings.filter(
    (f) => f.document_id === doc.id && f.page_num === state.currentPage
  );
  canvas.setFindings(pageFindings);
  canvas.selectById(state.activeFindingId);
}

async function loadWordsForPage() {
  const doc = currentDoc();
  if (!doc) return;
  try {
    const result = await API.getWords(doc.id, state.currentPage);
    canvas.setWords(result.words);
  } catch (_) {
    canvas.setWords([]);
  }
}

function updateViewerToolbar() {
  const doc = currentDoc();
  const redactedBtn = document.getElementById("view-redacted");
  const originalBtn = document.getElementById("view-original");
  redactedBtn.disabled = !(doc && doc.has_applied);
  redactedBtn.classList.toggle("active", state.showRedacted);
  originalBtn.classList.toggle("active", !state.showRedacted);
  document.getElementById("zoom-level").textContent = `${Math.round(state.zoom * 100)}%`;
}

// ---------------------------------------------------------------------------
// Popup menu

const popupMenu = document.getElementById("popup-menu");

function showPopup(items, point) {
  popupMenu.innerHTML = "";
  for (const item of items) {
    const btn = document.createElement("button");
    btn.className = "popup-item" + (item.danger ? " danger" : "");
    btn.textContent = item.label;
    btn.addEventListener("click", () => {
      hidePopup();
      item.onClick();
    });
    popupMenu.appendChild(btn);
  }
  popupMenu.classList.remove("hidden");
  const maxX = window.innerWidth - popupMenu.offsetWidth - 8;
  const maxY = window.innerHeight - popupMenu.offsetHeight - 8;
  popupMenu.style.left = `${Math.min(point.x, maxX)}px`;
  popupMenu.style.top = `${Math.min(point.y, maxY)}px`;
}

function hidePopup() {
  popupMenu.classList.add("hidden");
}

document.addEventListener("mousedown", (e) => {
  if (!popupMenu.contains(e.target)) hidePopup();
});

// ---------------------------------------------------------------------------
// Actions (shared with sidebar.js / review.js / rules.js)

const Actions = {
  scopeDocIds() {
    if (state.checkedDocIds.size) return [...state.checkedDocIds];
    return state.currentDocId ? [state.currentDocId] : [];
  },

  toggleDocChecked(docId, checked) {
    if (checked) state.checkedDocIds.add(docId);
    else state.checkedDocIds.delete(docId);
    renderDocList();
    refreshFindings();
  },

  async openDocument(docId) {
    if (state.currentDocId === docId) return;
    state.currentDocId = docId;
    state.currentPage = 0;
    state.activeFindingId = null;
    state.showRedacted = false;
    renderSidebar();
    updateViewerToolbar();
    if (!state.checkedDocIds.size) await refreshFindings();
    await loadPage();
  },

  async deleteDocument(docId) {
    const doc = state.documents.find((d) => d.id === docId);
    if (!confirm(`Remove ${doc ? doc.original_filename : "document"} from the project? The original file on disk is yours and unaffected.`)) return;
    await API.deleteDocument(docId);
    await refreshAll();
  },

  async goToPage(pageNum) {
    state.currentPage = pageNum;
    await loadPage();
  },

  async jumpToPage(docId, pageNum) {
    if (state.currentDocId !== docId) {
      state.currentDocId = docId;
      renderSidebar();
    }
    state.currentPage = pageNum;
    await loadPage();
  },

  async jumpToFinding(finding) {
    state.activeFindingId = finding.id;
    for (const key of groupKeysFor(finding)) state.expandedGroups.add(key);
    if (state.currentDocId !== finding.document_id) {
      state.currentDocId = finding.document_id;
      renderSidebar();
    }
    state.currentPage = finding.page_num;
    await loadPage();
    canvas.selectById(finding.id);
    renderReview();
    const card = document.querySelector(`[data-finding-id="${finding.id}"]`);
    if (card) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  },

  async setFindingStatus(findingId, status) {
    await API.updateFinding(findingId, { status });
    await refreshFindings();
    await refreshDocuments();
  },

  async deleteFinding(findingId) {
    await API.deleteFinding(findingId);
    if (state.activeFindingId === findingId) state.activeFindingId = null;
    await refreshFindings();
    await refreshDocuments();
  },

  async redactAllMatching(finding) {
    await API.bulkFindings("approve", {
      document_ids: Actions.scopeDocIds(),
      value_key: finding.value_key,
      entity_type: finding.entity_type,
    });
    await refreshFindings();
    await refreshDocuments();
  },

  async ignoreAllMatching(finding) {
    await API.bulkFindings("ignore", {
      document_ids: Actions.scopeDocIds(),
      value_key: finding.value_key,
      entity_type: finding.entity_type,
    });
    await refreshFindings();
    await refreshDocuments();
  },

  async bulkPage(docId, pageNum, action) {
    await API.bulkFindings(action, { document_ids: [docId], page_num: pageNum });
    await refreshFindings();
    await refreshDocuments();
  },

  async toggleReveal(findingId) {
    if (state.revealed[findingId] !== undefined) {
      delete state.revealed[findingId];
    } else {
      const result = await API.revealFinding(findingId);
      state.revealed[findingId] = result.text;
    }
    renderReview();
  },

  async createRuleFromFinding(finding) {
    let example = state.revealed[finding.id];
    if (example === undefined) {
      const result = await API.revealFinding(finding.id);
      example = result.text;
    }
    openRuleEditor(null, example || "");
  },

  async toggleRule(ruleId, enabled) {
    await API.updateRule(ruleId, { enabled });
    await Actions.refreshRules();
  },

  async refreshRules() {
    const result = await API.getRules();
    state.rules = result.rules;
    renderRulesList();
  },
};

// ---------------------------------------------------------------------------
// Canvas callbacks

canvas.onFindingSelected = (findingId) => {
  state.activeFindingId = findingId;
  if (findingId) {
    const finding = state.findings.find((f) => f.id === findingId);
    if (finding) {
      for (const key of groupKeysFor(finding)) state.expandedGroups.add(key);
    }
  }
  renderReview();
  if (findingId) {
    const card = document.querySelector(`[data-finding-id="${findingId}"]`);
    if (card) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
};

canvas.onBoxDrawn = (pdfRect, point) => {
  const doc = currentDoc();
  if (!doc) return;

  const create = async (options) => {
    await API.createManualFinding(doc.id, {
      page_num: state.currentPage,
      ...pdfRect,
      ...options,
    });
    await refreshFindings();
    await refreshDocuments();
  };

  showPopup(
    [
      { label: "Redact area (this page)", danger: true, onClick: () => create({}) },
      { label: "Apply to all pages", danger: true, onClick: () => create({ all_pages: true }) },
      { label: "Cancel", onClick: () => {} },
    ],
    point
  );
};

canvas.onTextSelected = (text, point) => {
  const preview = text.length > 40 ? `${text.slice(0, 37)}…` : text;
  showPopup(
    [
      {
        label: `Find similar: "${preview}"`,
        onClick: async () => {
          const result = await API.searchFindings(text, Actions.scopeDocIds());
          await refreshFindings();
          await refreshDocuments();
          alert(`${result.created} new finding(s) staged for review.`);
        },
      },
      { label: "Create rule from selection", onClick: () => openRuleEditor(null, text) },
      { label: "Cancel", onClick: () => {} },
    ],
    point
  );
};

canvas.onManualUpdated = async (findingId, bbox) => {
  try {
    await API.updateFinding(findingId, bbox);
  } finally {
    await refreshFindings();
  }
};

// ---------------------------------------------------------------------------
// Recognizer catalog (detection settings)

function getSelectedEntities() {
  const boxes = document.querySelectorAll(
    '#recognizer-catalog input[type="checkbox"][data-entity]:checked'
  );
  return Array.from(boxes).map((cb) => cb.dataset.entity);
}

function renderRecognizerGroup(title, recognizers) {
  const section = document.createElement("div");
  section.className = "recognizer-group";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.appendChild(heading);

  for (const recognizer of recognizers) {
    const option = document.createElement("div");
    option.className = "recognizer-option";
    const id = `recognizer-${recognizer.entity_type}`;
    option.innerHTML = `
      <input type="checkbox" id="${id}" data-entity="${recognizer.entity_type}" ${recognizer.default_enabled ? "checked" : ""}>
      <label for="${id}" title="${recognizer.description}">${recognizer.label}</label>
    `;
    section.appendChild(option);
  }
  return section;
}

async function loadRecognizerCatalog() {
  const container = document.getElementById("recognizer-catalog");
  try {
    const result = await API.getRecognizers();
    const recognizers = result.recognizers || [];
    state.recognizers = recognizers;
    container.innerHTML = "";

    if (recognizers.length === 1 && recognizers[0].entity_type === "_error") {
      container.innerHTML = `<p class="hint">${recognizers[0].description}</p>`;
      return;
    }

    const custom = recognizers.filter((r) => r.group === "custom");
    const builtin = recognizers.filter((r) => r.group === "builtin");
    if (custom.length) container.appendChild(renderRecognizerGroup("Custom", custom));
    if (builtin.length) container.appendChild(renderRecognizerGroup("Built-in", builtin));

    const typeFilter = document.getElementById("filter-type");
    for (const r of recognizers) {
      const opt = document.createElement("option");
      opt.value = r.entity_type;
      opt.textContent = r.label;
      typeFilter.appendChild(opt);
    }
    for (const extra of [["MANUAL", "Manual box"], ["CUSTOM_SEARCH", "Search match"]]) {
      const opt = document.createElement("option");
      opt.value = extra[0];
      opt.textContent = extra[1];
      typeFilter.appendChild(opt);
    }
  } catch (err) {
    container.innerHTML = `<p class="hint">${err.message}</p>`;
  }
}

// ---------------------------------------------------------------------------
// Batch operations

function requireScope() {
  const ids = Actions.scopeDocIds();
  if (!ids.length) {
    alert("Import and select documents first.");
    return null;
  }
  return ids;
}

async function startBatchDetect() {
  const ids = requireScope();
  if (!ids) return;
  const entities = getSelectedEntities();
  const threshold = parseFloat(document.getElementById("score-threshold").value) || 0.5;
  try {
    await API.batchDetect(ids, entities.length ? entities : null, threshold);
    await refreshDocuments();
  } catch (err) {
    alert(`Detect failed: ${err.message}`);
  }
}

async function startBatchApply() {
  const ids = requireScope();
  if (!ids) return;
  const approved = state.findings.filter(
    (f) => ids.includes(f.document_id) && f.status === "approved"
  ).length;
  if (!approved) {
    alert("No approved findings to apply. Mark findings for redaction first.");
    return;
  }
  if (!confirm(
    `Permanently apply ${approved} redaction(s) to the working copies of ${ids.length} document(s)?\n` +
    "Originals are never modified. A verification pass runs automatically."
  )) return;
  try {
    await API.batchApply(ids);
    await refreshDocuments();
  } catch (err) {
    alert(`Apply failed: ${err.message}`);
  }
}

async function startBatchVerify() {
  const ids = requireScope();
  if (!ids) return;
  try {
    await API.batchVerify(ids);
    await refreshDocuments();
  } catch (err) {
    alert(`Verify failed: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Export dialog

const exportModal = document.getElementById("export-modal");
let exportDocIds = [];

function verificationSummaryHtml(report) {
  if (!report) return "";
  let html = "<ul class='verify-checks'>";
  for (const check of report.checks) {
    html += `<li class="${check.passed ? "pass" : "fail"}">${check.passed ? "✓" : "✗"} ${check.label}${check.detail ? ` — ${check.detail}` : ""}</li>`;
  }
  html += "</ul>";
  if (report.residual_findings.length) {
    html += "<p class='fail'>Potential remaining PII:</p><ul class='verify-checks'>";
    for (const r of report.residual_findings) {
      html += `<li class="fail">${r.entity_type} — ${r.masked_text} (p. ${r.page_num + 1})</li>`;
    }
    html += "</ul>";
  }
  return html;
}

async function openExportModal() {
  exportDocIds = requireScope();
  if (!exportDocIds) return;

  document.getElementById("export-results").innerHTML = "";
  document.getElementById("export-anyway-btn").classList.add("hidden");
  document.getElementById("export-review-btn").classList.add("hidden");
  document.getElementById("export-confirm-btn").classList.remove("hidden");

  const summary = document.getElementById("export-summary");
  summary.innerHTML = "<p class='hint'>Checking documents…</p>";
  exportModal.classList.remove("hidden");

  let html = "";
  let anyIssue = false;
  for (const docId of exportDocIds) {
    const doc = state.documents.find((d) => d.id === docId);
    if (!doc) continue;
    const counts = doc.finding_counts || {};
    const unresolved = (counts.pending || 0) + (counts.needs_review || 0);

    let status;
    if (!doc.has_applied) {
      status = '<span class="fail">no applied redactions</span>';
      anyIssue = true;
    } else if (doc.verification_passed === true) {
      status = '<span class="pass">verification passed</span>';
    } else if (doc.verification_passed === false) {
      status = '<span class="fail">verification found issues</span>';
      anyIssue = true;
    } else {
      status = '<span class="hint">not verified yet (will verify on export)</span>';
    }
    if (unresolved) {
      status += ` · <span class="fail">${unresolved} unresolved finding(s)</span>`;
      anyIssue = true;
    }

    html += `<div class="export-doc-row"><strong>${doc.original_filename}</strong><br>${status}`;
    if (doc.has_applied && doc.verification_passed === false) {
      try {
        const report = await API.getVerification(doc.id);
        html += verificationSummaryHtml(report);
      } catch (_) { /* no report */ }
    }
    html += "</div>";
  }
  if (anyIssue) {
    html += "<p class='fail'>Some documents have unresolved issues. Export will skip them unless you choose Export anyway.</p>";
    document.getElementById("export-review-btn").classList.remove("hidden");
  }
  summary.innerHTML = html || "<p class='hint'>Nothing to export.</p>";
}

async function runExport(allowUnverified) {
  const resultsEl = document.getElementById("export-results");
  resultsEl.innerHTML = "<p class='hint'>Exporting…</p>";
  try {
    const result = await API.batchExport(exportDocIds, allowUnverified);
    let html = "";
    if (result.warnings.length) {
      html += "<ul class='verify-checks'>" +
        result.warnings.map((w) => `<li class="fail">⚠ ${w}</li>`).join("") +
        "</ul>";
    }
    html += "<ul class='export-links'>";
    for (const item of result.items) {
      const doc = state.documents.find((d) => d.id === item.document_id);
      const name = doc ? doc.original_filename : item.document_id;
      if (item.download_url) {
        html += `<li class="pass"><a href="${item.download_url}" download>⬇ ${item.filename}</a></li>`;
      } else {
        html += `<li class="fail">${name}: ${item.skipped_reason}</li>`;
      }
    }
    html += "</ul>";
    if (result.zip_url) {
      html += `<p><a class="btn small primary" href="${result.zip_url}" download>⬇ Download batch ZIP (PDFs + audit report + CSV + verification report)</a></p>`;
    }
    resultsEl.innerHTML = html;

    const anySkipped = result.items.some((i) => i.skipped_reason);
    document.getElementById("export-anyway-btn").classList.toggle("hidden", !anySkipped || allowUnverified);
    document.getElementById("export-confirm-btn").classList.add("hidden");
    await refreshDocuments();
  } catch (err) {
    resultsEl.innerHTML = `<p class="fail">Export failed: ${err.message}</p>`;
  }
}

// ---------------------------------------------------------------------------
// Event wiring

function initEvents() {
  // Upload
  const fileInput = document.getElementById("file-input");
  document.getElementById("upload-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    if (!fileInput.files.length) return;
    try {
      const result = await API.upload(fileInput.files);
      if (result.errors.length) alert(result.errors.join("\n"));
      for (const doc of result.documents) state.checkedDocIds.add(doc.id);
      if (result.documents.length) {
        state.currentDocId = result.documents[0].id;
        state.currentPage = 0;
      }
      await refreshAll();
    } catch (err) {
      alert(`Import failed: ${err.message}`);
    } finally {
      fileInput.value = "";
    }
  });

  document.getElementById("select-all-docs").addEventListener("change", (e) => {
    state.checkedDocIds = e.target.checked
      ? new Set(state.documents.map((d) => d.id))
      : new Set();
    renderDocList();
    refreshFindings();
  });

  // Batch bar
  document.getElementById("batch-detect-btn").addEventListener("click", startBatchDetect);
  document.getElementById("batch-apply-btn").addEventListener("click", startBatchApply);
  document.getElementById("batch-verify-btn").addEventListener("click", startBatchVerify);
  document.getElementById("batch-export-btn").addEventListener("click", openExportModal);

  // Collapsible panels
  document.querySelectorAll(".toggle-panel").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = document.getElementById(btn.dataset.target);
      body.classList.toggle("collapsed");
      btn.textContent = body.classList.contains("collapsed") ? "▾" : "▴";
    });
  });

  // Viewer toolbar
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      canvas.setMode(btn.dataset.mode);
    });
  });

  document.getElementById("zoom-in").addEventListener("click", () => {
    state.zoom = Math.min(4, state.zoom * 1.25);
    canvas.setZoom(state.zoom);
    updateViewerToolbar();
  });
  document.getElementById("zoom-out").addEventListener("click", () => {
    state.zoom = Math.max(0.25, state.zoom / 1.25);
    canvas.setZoom(state.zoom);
    updateViewerToolbar();
  });

  document.getElementById("prev-page").addEventListener("click", async () => {
    if (state.currentPage > 0) {
      state.currentPage -= 1;
      await loadPage();
    }
  });
  document.getElementById("next-page").addEventListener("click", async () => {
    const doc = currentDoc();
    if (doc && state.currentPage < doc.page_count - 1) {
      state.currentPage += 1;
      await loadPage();
    }
  });

  document.getElementById("view-original").addEventListener("click", async () => {
    state.showRedacted = false;
    updateViewerToolbar();
    await loadPage();
  });
  document.getElementById("view-redacted").addEventListener("click", async () => {
    state.showRedacted = true;
    updateViewerToolbar();
    await loadPage();
  });

  // Review pane
  document.getElementById("page-view-btn").addEventListener("click", () => {
    state.viewMode = "page";
    document.getElementById("page-view-btn").classList.add("active");
    document.getElementById("pii-view-btn").classList.remove("active");
    renderReview();
  });
  document.getElementById("pii-view-btn").addEventListener("click", () => {
    state.viewMode = "pii";
    document.getElementById("pii-view-btn").classList.add("active");
    document.getElementById("page-view-btn").classList.remove("active");
    renderReview();
  });

  document.getElementById("filter-type").addEventListener("change", (e) => {
    state.filters.entityType = e.target.value;
    renderReview();
  });
  document.getElementById("filter-status").addEventListener("change", (e) => {
    state.filters.status = e.target.value;
    renderReview();
  });
  document.getElementById("filter-source").addEventListener("change", (e) => {
    state.filters.source = e.target.value;
    renderReview();
  });
  document.getElementById("filter-confidence").addEventListener("change", (e) => {
    const value = parseFloat(e.target.value);
    state.filters.minConfidence = Number.isNaN(value) ? null : value;
    renderReview();
  });

  document.getElementById("redact-selected-btn").addEventListener("click", async () => {
    if (!state.selectedFindingIds.size) {
      alert("Tick findings in the list first.");
      return;
    }
    await API.bulkFindings("approve", { finding_ids: [...state.selectedFindingIds] });
    state.selectedFindingIds.clear();
    await refreshFindings();
    await refreshDocuments();
  });
  document.getElementById("ignore-selected-btn").addEventListener("click", async () => {
    if (!state.selectedFindingIds.size) {
      alert("Tick findings in the list first.");
      return;
    }
    await API.bulkFindings("ignore", { finding_ids: [...state.selectedFindingIds] });
    state.selectedFindingIds.clear();
    await refreshFindings();
    await refreshDocuments();
  });
  document.getElementById("redact-highconf-btn").addEventListener("click", async () => {
    const ids = requireScope();
    if (!ids) return;
    const result = await API.bulkFindings("approve", {
      document_ids: ids,
      min_confidence: 0.85,
      status: ["pending", "needs_review"],
    });
    await refreshFindings();
    await refreshDocuments();
    alert(`${result.updated} high-confidence finding(s) marked for redaction.`);
  });

  // Rules
  document.getElementById("new-rule-btn").addEventListener("click", () => openRuleEditor());

  // Export modal
  document.getElementById("export-modal-close").addEventListener("click", () =>
    exportModal.classList.add("hidden"));
  document.getElementById("export-cancel-btn").addEventListener("click", () =>
    exportModal.classList.add("hidden"));
  document.getElementById("export-confirm-btn").addEventListener("click", () => runExport(false));
  document.getElementById("export-anyway-btn").addEventListener("click", () => {
    if (confirm("Export anyway with unresolved verification issues?")) runExport(true);
  });
  document.getElementById("export-review-btn").addEventListener("click", () => {
    exportModal.classList.add("hidden");
    state.filters.status = "pending";
    document.getElementById("filter-status").value = "pending";
    renderReview();
  });

  // Keyboard: delete selected manual finding
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Delete" || e.key === "Backspace") &&
        !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      const finding = state.findings.find((f) => f.id === state.activeFindingId);
      if (finding && finding.source === "manual" && finding.status !== "applied") {
        Actions.deleteFinding(finding.id);
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Boot

async function init() {
  initRuleModal();
  initEvents();
  // The recognizer catalog builds the Presidio analyzer on first call (slow);
  // don't block the document list on it.
  await Promise.all([loadRecognizerCatalog(), Actions.refreshRules(), refreshAll()]);
  renderReview();
}

init();
