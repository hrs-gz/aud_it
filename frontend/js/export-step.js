/* Step 3: Review and export. */

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

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

const exportStepState = {
  showRedacted: false,
  previewDocId: null,
  previewPage: 0,
};

async function loadExportView() {
  if (!state.currentProjectId) return;
  showView("export");
  updateStepBreadcrumb("export", state.currentProject);
  await refreshDocuments();
  await renderExportStep();
}

async function renderExportStep({ preserveResults = false } = {}) {
  const summaryEl = document.getElementById("export-step-summary");
  const resultsEl = document.getElementById("export-step-results");
  const docSelect = document.getElementById("export-preview-doc");

  const docs = state.documents.filter((d) => d.is_materialized !== false);
  if (!docs.length) {
    summaryEl.innerHTML = "<p class='hint'>No materialized documents to export.</p>";
    resultsEl.innerHTML = "";
    docSelect.innerHTML = "";
    return;
  }

  let html = "";
  let anyIssue = false;
  for (const doc of docs) {
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
      status = '<span class="hint">not verified yet</span>';
    }
    if (unresolved) {
      status += ` · <span class="fail">${unresolved} unresolved</span>`;
      anyIssue = true;
    }
    html += `<div class="export-doc-row"><strong>${escapeHtml(doc.original_filename)}</strong><br>${status}`;
    if (doc.has_applied && doc.verification_passed === false) {
      try {
        const report = await API.getVerification(doc.id);
        html += verificationSummaryHtml(report);
      } catch (_) { /* skip */ }
    }
    html += "</div>";
  }
  summaryEl.innerHTML = html;
  if (!preserveResults) {
    resultsEl.innerHTML = "";
    document.getElementById("export-step-anyway-btn").classList.add("hidden");
    document.getElementById("export-step-run-btn").classList.remove("hidden");
  }

  docSelect.innerHTML = docs
    .map(
      (d) =>
        `<option value="${d.id}">${escapeHtml(d.original_filename)}</option>`
    )
    .join("");
  const selectedDocId = docs.some((d) => d.id === exportStepState.previewDocId)
    ? exportStepState.previewDocId
    : docs[0].id;
  if (selectedDocId !== exportStepState.previewDocId) {
    exportStepState.previewPage = 0;
  }
  exportStepState.previewDocId = selectedDocId;
  docSelect.value = selectedDocId;
  await updateExportPreview();
}

async function updateExportPreview() {
  const img = document.getElementById("export-preview-image");
  const empty = document.getElementById("export-preview-empty");
  const doc = state.documents.find((d) => d.id === exportStepState.previewDocId);
  if (!doc) {
    img.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }
  const version = exportStepState.showRedacted ? "redacted" : "original";
  if (exportStepState.showRedacted && !doc.has_applied) {
    img.classList.add("hidden");
    empty.textContent = "No redacted preview — apply redactions first.";
    empty.classList.remove("hidden");
    return;
  }
  img.src = API.pageImageUrl(doc.id, exportStepState.previewPage, version);
  img.classList.remove("hidden");
  empty.classList.add("hidden");

  document.getElementById("export-preview-redacted").disabled = !doc.has_applied;
}

async function runExportStep(allowUnverified) {
  const docs = state.documents.filter((d) => !d.archived);
  const ids = docs.map((d) => d.id);
  if (!ids.length) return;

  const resultsEl = document.getElementById("export-step-results");
  resultsEl.innerHTML = "<p class='hint'>Exporting…</p>";
  try {
    const result = await API.batchExport(ids, allowUnverified);
    let html = "";
    if (result.warnings.length) {
      html +=
        "<ul class='verify-checks'>" +
        result.warnings.map((w) => `<li class="fail">⚠ ${escapeHtml(w)}</li>`).join("") +
        "</ul>";
    }
    html += "<ul class='export-links'>";
    for (const item of result.items) {
      const doc = docs.find((d) => d.id === item.document_id);
      const name = doc ? doc.original_filename : item.document_id;
      if (item.download_url) {
        html += `<li class="pass"><a href="${item.download_url}" download>⬇ ${escapeHtml(item.filename || name)}</a></li>`;
      } else {
        html += `<li class="fail">${escapeHtml(name)}: ${escapeHtml(item.skipped_reason || "skipped")}</li>`;
      }
    }
    html += "</ul>";
    if (result.zip_url) {
      html += `<p><a class="btn primary" href="${result.zip_url}" download>⬇ Download project ZIP (PDFs + reports)</a></p>`;
    }
    resultsEl.innerHTML = html;

    const anySkipped = result.items.some((i) => i.skipped_reason);
    document.getElementById("export-step-anyway-btn").classList.toggle(
      "hidden",
      !anySkipped || allowUnverified
    );
    document.getElementById("export-step-run-btn").classList.toggle("hidden", anySkipped && !allowUnverified);

    await API.updateProject(state.currentProjectId, { step: "export" });
    state.currentProject = await API.getProject(state.currentProjectId);
    await refreshDocuments();
    await renderExportStep({ preserveResults: true });
    resultsEl.innerHTML = html;
  } catch (err) {
    resultsEl.innerHTML = `<p class="fail">Export failed: ${escapeHtml(err.message)}</p>`;
  }
}

function initExportStep() {
  document.getElementById("export-step-back-btn").addEventListener("click", () => {
    Router.navigate("redact", state.currentProjectId, "redact");
  });

  document.getElementById("export-step-run-btn").addEventListener("click", () => runExportStep(false));
  document.getElementById("export-step-anyway-btn").addEventListener("click", () => {
    if (confirm("Export anyway with unresolved verification issues?")) runExportStep(true);
  });

  document.getElementById("export-preview-doc").addEventListener("change", async (e) => {
    exportStepState.previewDocId = e.target.value;
    exportStepState.previewPage = 0;
    await updateExportPreview();
  });

  document.getElementById("export-preview-original").addEventListener("click", async () => {
    exportStepState.showRedacted = false;
    document.getElementById("export-preview-original").classList.add("active");
    document.getElementById("export-preview-redacted").classList.remove("active");
    await updateExportPreview();
  });

  document.getElementById("export-preview-redacted").addEventListener("click", async () => {
    exportStepState.showRedacted = true;
    document.getElementById("export-preview-redacted").classList.add("active");
    document.getElementById("export-preview-original").classList.remove("active");
    await updateExportPreview();
  });
}
