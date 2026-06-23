/* App state, actions, and wiring for the three-panel review workflow. */

const state = {
  projects: [],
  currentProjectId: null,
  currentProject: null,
  currentStep: null,
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
  zoomIsFit: true,
  lastFitKey: null,
  paneVisibility: { left: true, right: true },
  presidioStatus: "loading",
  rules: [],
  recognizers: [],
  pollTimer: null,
  documentsRefreshGen: 0,
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
  const projectId = state.currentProjectId;
  if (!projectId) return;
  const gen = ++state.documentsRefreshGen;
  const result = await API.listDocuments(projectId);
  if (gen !== state.documentsRefreshGen) return;

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
  updateStepActions();
  updateViewerToolbar();
  schedulePollingIfBusy();
}

function resetViewerForEmptyDocList() {
  state.activeFindingId = null;
  state.showRedacted = false;
  const selectAll = document.getElementById("select-all-docs");
  if (selectAll) selectAll.checked = false;
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

async function loadRedactView() {
  if (!state.currentProjectId) return;
  showView("redact");
  updateStepBreadcrumb("redact", state.currentProject);
  state.currentProject = await API.getProject(state.currentProjectId);
  await refreshAll();
}

async function handleRoute(route) {
  if (route.view === "dashboard") {
    await loadDashboardView();
    return;
  }

  try {
    state.currentProject = await API.getProject(route.projectId);
    state.currentProjectId = route.projectId;
    state.currentStep = route.step;

    const order = ["organize", "redact", "export"];
    const savedIdx = order.indexOf(state.currentProject.step || "organize");
    const targetIdx = order.indexOf(route.step);

    if (targetIdx > savedIdx) {
      Router.navigate(state.currentProject.step, route.projectId, state.currentProject.step);
      return;
    }

    if (route.step === "organize") await loadOrganizeView();
    else if (route.step === "redact") await loadRedactView();
    else if (route.step === "export") await loadExportView();
  } catch (err) {
    alert(err.message);
    Router.navigate("dashboard");
  }
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function clearProjectSession() {
  stopPolling();
  state.documents = [];
  state.checkedDocIds = new Set();
  state.currentDocId = null;
  state.currentPage = 0;
  state.findings = [];
  state.revealed = {};
  state.selectedFindingIds = new Set();
  state.activeFindingId = null;
  state.currentStep = null;
  const statusEl = document.getElementById("global-status");
  if (statusEl) statusEl.innerHTML = "";
  hidePopup();
  if (typeof closeRuleEditor === "function") closeRuleEditor();
}

function schedulePollingIfBusy() {
  if (!state.currentProjectId) return;
  const busy = state.documents.some((d) => BUSY_STATUSES.has(d.status));
  if (busy && !state.pollTimer) {
    state.pollTimer = setTimeout(async () => {
      state.pollTimer = null;
      if (!state.currentProjectId) return;
      try {
        const wasBusy = state.documents.some((d) => BUSY_STATUSES.has(d.status));
        await refreshDocuments();
        const stillBusy = state.documents.some((d) => BUSY_STATUSES.has(d.status));
        if (wasBusy && !stillBusy) {
          await refreshFindings();
          await loadPage();
        }
      } catch (err) {
        console.error("Document poll failed:", err);
      } finally {
        schedulePollingIfBusy();
      }
    }, 1200);
  }
}

function renderGlobalStatus() {
  const el = document.getElementById("global-status");
  const parts = [];

  if (state.presidioStatus === "loading") {
    parts.push("Loading detection engine…");
  } else if (state.presidioStatus === "error") {
    parts.push('<span class="fail">Detection engine unavailable</span>');
  }

  const counts = {};
  for (const doc of state.documents) {
    if (BUSY_STATUSES.has(doc.status)) counts[doc.status] = (counts[doc.status] || 0) + 1;
  }
  parts.push(
    ...Object.entries(counts).map(([status, n]) => {
      const labels = {
        ocr: "Running OCR",
        detecting: "Detecting",
        applying: "Applying redactions",
        verifying: "Verifying",
        exporting: "Exporting",
      };
      return `${labels[status] || status} ${n} doc(s)`;
    })
  );
  const errors = state.documents.filter((d) => d.status === "error").length;
  if (errors) parts.push(`<span class="fail">${errors} error(s)</span>`);

  const showSpinner = state.presidioStatus === "loading" || Object.keys(counts).length > 0;
  el.innerHTML = parts.length
    ? `${showSpinner ? '<span class="spinner"></span> ' : ""}${parts.join(" · ")}`
    : "";
}

function updateDetectButtonState() {
  const btn = document.getElementById("batch-detect-btn");
  if (!btn) return;
  const ready = state.presidioStatus === "ready";
  btn.disabled = !ready;
  btn.title = ready ? "" : "Waiting for detection engine to finish loading";
}

// ---------------------------------------------------------------------------
// Viewer

function computeFitZoom(img) {
  const viewerEl = document.getElementById("viewer-scroll");
  if (!viewerEl || !img) return 1;
  const pad = 24;
  const fitW = (viewerEl.clientWidth - pad) / img.width;
  const fitH = (viewerEl.clientHeight - pad) / img.height;
  const fit = Math.min(fitW, fitH);
  return Math.min(4, Math.max(0.25, fit));
}

async function applyFitZoomIfNeeded() {
  if (!state.zoomIsFit || !canvas.img) return;
  state.zoom = computeFitZoom(canvas.img);
  canvas.setZoom(state.zoom);
  updateViewerToolbar();
}

function loadPaneVisibility() {
  try {
    const saved = localStorage.getItem("aud_it_pane_visibility");
    if (saved) state.paneVisibility = { ...state.paneVisibility, ...JSON.parse(saved) };
  } catch (_) { /* ignore */ }
}

function savePaneVisibility() {
  try {
    localStorage.setItem("aud_it_pane_visibility", JSON.stringify(state.paneVisibility));
  } catch (_) { /* ignore */ }
}

function applyPaneVisibility() {
  const layout = document.getElementById("view-redact");
  if (!layout) return;
  layout.classList.toggle("left-hidden", !state.paneVisibility.left);
  layout.classList.toggle("right-hidden", !state.paneVisibility.right);

  const toggleLeft = document.getElementById("toggle-left-pane");
  const toggleRight = document.getElementById("toggle-right-pane");
  if (toggleLeft) toggleLeft.classList.toggle("active", state.paneVisibility.left);
  if (toggleRight) toggleRight.classList.toggle("active", state.paneVisibility.right);

  const restoreLeft = document.getElementById("restore-left-pane");
  const restoreRight = document.getElementById("restore-right-pane");
  if (restoreLeft) restoreLeft.classList.toggle("hidden", state.paneVisibility.left);
  if (restoreRight) restoreRight.classList.toggle("hidden", state.paneVisibility.right);

  applyFitZoomIfNeeded();
}

function togglePane(side) {
  state.paneVisibility[side] = !state.paneVisibility[side];
  savePaneVisibility();
  applyPaneVisibility();
}

let resizeFitTimer = null;
function scheduleFitZoomOnResize() {
  clearTimeout(resizeFitTimer);
  resizeFitTimer = setTimeout(() => applyFitZoomIfNeeded(), 150);
}

async function loadPage() {
  const doc = currentDoc();
  const emptyEl = document.getElementById("viewer-empty");
  const container = document.getElementById("canvas-container");

  if (!doc) {
    emptyEl.classList.remove("hidden");
    container.classList.add("hidden");
    canvas.clear();
    state.activeFindingId = null;
    state.showRedacted = false;
    state.currentPage = 0;
    document.getElementById("page-indicator").textContent = "—";
    const selectAll = document.getElementById("select-all-docs");
    if (selectAll) selectAll.checked = false;
    updateViewerToolbar();
    renderPageStrip();
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

  const fitKey = `${doc.id}:${state.currentPage}`;
  if (fitKey !== state.lastFitKey) {
    state.zoomIsFit = true;
    state.lastFitKey = fitKey;
  }
  if (state.zoomIsFit && canvas.img) {
    state.zoom = computeFitZoom(canvas.img);
    canvas.setZoom(state.zoom);
    updateViewerToolbar();
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

function exportStepReadiness() {
  const docs = state.documents.filter((d) => !d.archived);
  if (!docs.length) {
    return { ok: false, message: "Import documents and complete redaction before exporting." };
  }
  const busy = docs.filter((d) => BUSY_STATUSES.has(d.status));
  if (busy.length) {
    return {
      ok: false,
      message: "Wait for background processing to finish before continuing to export.",
    };
  }
  if (docs.some((d) => !d.has_applied)) {
    return {
      ok: false,
      message: "Apply redactions to all project documents before continuing to export.",
    };
  }
  if (docs.some((d) => !d.verified_at)) {
    return {
      ok: false,
      message: "Run verification or wait for automatic verification to finish before exporting.",
    };
  }
  return { ok: true, message: "" };
}

function updateStepActions() {
  const continueBtn = document.getElementById("continue-export-btn");
  if (!continueBtn) return;
  const readiness = exportStepReadiness();
  continueBtn.disabled = !readiness.ok;
  continueBtn.title = readiness.ok ? "" : readiness.message;
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

    stopPolling();
    state.documentsRefreshGen++;

    const snapshot = {
      documents: state.documents,
      currentDocId: state.currentDocId,
      currentPage: state.currentPage,
      checkedDocIds: new Set(state.checkedDocIds),
      lastFitKey: state.lastFitKey,
      activeFindingId: state.activeFindingId,
      showRedacted: state.showRedacted,
    };

    state.documents = state.documents.filter((d) => d.id !== docId);
    state.checkedDocIds.delete(docId);
    if (state.currentDocId === docId) {
      state.currentDocId = state.documents[0]?.id ?? null;
      state.currentPage = 0;
      state.lastFitKey = null;
    }
    if (!state.documents.length) {
      resetViewerForEmptyDocList();
    }

    renderSidebar();
    updateViewerToolbar();
    await refreshFindings();
    await loadPage();

    try {
      await API.deleteDocument(docId);
      await refreshDocuments();
      await refreshFindings();
      await loadPage();
    } catch (err) {
      state.documents = snapshot.documents;
      state.currentDocId = snapshot.currentDocId;
      state.currentPage = snapshot.currentPage;
      state.checkedDocIds = snapshot.checkedDocIds;
      state.lastFitKey = snapshot.lastFitKey;
      state.activeFindingId = snapshot.activeFindingId;
      state.showRedacted = snapshot.showRedacted;
      renderSidebar();
      updateViewerToolbar();
      await refreshFindings();
      await loadPage();
      alert(err.message);
    }
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

  async markAllMatching(finding) {
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

canvas.onFindingsMarqueeSelected = (ids, additive) => {
  if (additive) {
    for (const id of ids) state.selectedFindingIds.add(id);
  } else {
    state.selectedFindingIds = new Set(ids);
  }
  if (ids.length) {
    state.activeFindingId = ids[ids.length - 1];
    canvas.selectById(state.activeFindingId);
    const finding = state.findings.find((f) => f.id === state.activeFindingId);
    if (finding) {
      for (const key of groupKeysFor(finding)) state.expandedGroups.add(key);
    }
  }
  renderReview();
  if (state.activeFindingId) {
    const card = document.querySelector(`[data-finding-id="${state.activeFindingId}"]`);
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
      { label: "Mark area (this page)", onClick: () => create({}) },
      { label: "Mark area (all pages)", onClick: () => create({ all_pages: true }) },
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
  if (state.presidioStatus === "loading") {
    container.innerHTML = '<p class="hint">Loading recognizers...</p>';
    return;
  }
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
  updateDetectButtonState();
}

async function waitForPresidioReady() {
  const container = document.getElementById("recognizer-catalog");
  container.innerHTML = '<p class="hint">Loading recognizers...</p>';
  updateDetectButtonState();
  renderGlobalStatus();

  while (true) {
    try {
      const status = await API.getPresidioStatus();
      state.presidioStatus = status.status;
      if (status.status === "ready" || status.status === "error") {
        renderGlobalStatus();
        await loadRecognizerCatalog();
        return;
      }
    } catch (_) {
      state.presidioStatus = "error";
      renderGlobalStatus();
      await loadRecognizerCatalog();
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
    renderGlobalStatus();
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
// Event wiring

function initEvents() {
  // Upload
  const fileInput = document.getElementById("file-input");
  document.getElementById("upload-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    if (!fileInput.files.length) return;
    try {
      const result = await API.upload(fileInput.files, state.currentProjectId);
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
  document.getElementById("continue-export-btn").addEventListener("click", async () => {
    const readiness = exportStepReadiness();
    if (!readiness.ok) {
      alert(readiness.message);
      return;
    }
    if (state.currentProjectId) {
      await API.updateProject(state.currentProjectId, { step: "export" });
      state.currentProject = await API.getProject(state.currentProjectId);
      Router.navigate("export", state.currentProjectId, "export");
    }
  });

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
    state.zoomIsFit = false;
    state.zoom = Math.min(4, state.zoom * 1.25);
    canvas.setZoom(state.zoom);
    updateViewerToolbar();
  });
  document.getElementById("zoom-out").addEventListener("click", () => {
    state.zoomIsFit = false;
    state.zoom = Math.max(0.25, state.zoom / 1.25);
    canvas.setZoom(state.zoom);
    updateViewerToolbar();
  });

  document.getElementById("toggle-left-pane").addEventListener("click", () => togglePane("left"));
  document.getElementById("toggle-right-pane").addEventListener("click", () => togglePane("right"));
  document.getElementById("restore-left-pane").addEventListener("click", () => {
    if (!state.paneVisibility.left) togglePane("left");
  });
  document.getElementById("restore-right-pane").addEventListener("click", () => {
    if (!state.paneVisibility.right) togglePane("right");
  });
  window.addEventListener("resize", scheduleFitZoomOnResize);

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

  document.getElementById("mark-selected-btn").addEventListener("click", async () => {
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
  document.getElementById("mark-highconf-btn").addEventListener("click", async () => {
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

  // Keyboard shortcuts on review page
  document.addEventListener("keydown", async (e) => {
    if (!isReviewKeyboardContext()) return;

    if (e.key === "Delete") {
      const finding = state.findings.find((f) => f.id === state.activeFindingId);
      if (finding && finding.source === "manual" && finding.status !== "applied") {
        e.preventDefault();
        Actions.deleteFinding(finding.id);
      }
      return;
    }

    if (e.key === "Backspace") {
      const finding = state.findings.find((f) => f.id === state.activeFindingId);
      if (finding && finding.source === "manual" && finding.status !== "applied") {
        e.preventDefault();
        Actions.deleteFinding(finding.id);
        return;
      }
      const ids = actionableFindingIds(getKeyboardTargetFindingIds());
      if (ids.length) {
        e.preventDefault();
        await API.bulkFindings("ignore", { finding_ids: ids });
        state.selectedFindingIds.clear();
        await refreshFindings();
        await refreshDocuments();
      }
      return;
    }

    if (e.key === "Enter") {
      const ids = actionableFindingIds(getKeyboardTargetFindingIds());
      if (ids.length) {
        e.preventDefault();
        await API.bulkFindings("approve", { finding_ids: ids });
        state.selectedFindingIds.clear();
        await refreshFindings();
        await refreshDocuments();
      }
    }
  });
}

function isReviewKeyboardContext() {
  if (Router.parse().view !== "redact") return false;
  const tag = document.activeElement?.tagName;
  return !["INPUT", "TEXTAREA", "SELECT"].includes(tag);
}

function getKeyboardTargetFindingIds() {
  if (state.selectedFindingIds.size) {
    return [...state.selectedFindingIds];
  }
  if (state.activeFindingId) {
    return [state.activeFindingId];
  }
  return [];
}

function actionableFindingIds(ids) {
  return ids.filter((id) => {
    const finding = state.findings.find((f) => f.id === id);
    return finding && finding.status !== "applied";
  });
}

// ---------------------------------------------------------------------------
// Boot

async function init() {
  initRuleModal();
  initRouter();
  initDashboard();
  initOrganize();
  initExportStep();
  loadPaneVisibility();
  applyPaneVisibility();
  initEvents();
  Router.onRoute(handleRoute);
  updateDetectButtonState();
  waitForPresidioReady();
  Actions.refreshRules();
}

init();
