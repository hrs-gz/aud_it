let currentDoc = null;
let currentPage = 0;
let piiSuggestions = [];

const pageCanvas = document.getElementById("page-canvas");
const overlayCanvas = document.getElementById("overlay-canvas");
const container = document.getElementById("canvas-container");
const canvas = new RedactionCanvas(pageCanvas, overlayCanvas, container);

const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const docInfo = document.getElementById("doc-info");
const scannedBadge = document.getElementById("scanned-badge");
const ocrBtn = document.getElementById("ocr-btn");
const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const bulkRedactBtn = document.getElementById("bulk-redact-btn");
const searchResults = document.getElementById("search-results");
const exportBtn = document.getElementById("export-btn");
const exportStatus = document.getElementById("export-status");
const prevPageBtn = document.getElementById("prev-page");
const nextPageBtn = document.getElementById("next-page");
const pageIndicator = document.getElementById("page-indicator");
const detectPiiBtn = document.getElementById("detect-pii-btn");
const applyPiiBtn = document.getElementById("apply-pii-btn");
const piiResults = document.getElementById("pii-results");

canvas.onRedactionCreated = async (pdfRect) => {
  if (!currentDoc) return;
  const created = await API.createRedaction(currentDoc.id, {
    page_num: currentPage,
    ...pdfRect,
    source: "manual",
  });
  await loadRedactions();
  canvas.selectById(created.id);
};

canvas.onRedactionUpdated = async (id, pdfRect) => {
  await API.updateRedaction(id, pdfRect);
  await loadRedactions();
};

canvas.onRedactionDeleted = async (id) => {
  await API.deleteRedaction(id);
  await loadRedactions();
};

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    canvas.setMode(btn.dataset.mode);
  });
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Delete" || e.key === "Backspace") {
    if (document.activeElement.tagName !== "INPUT") {
      canvas.deleteSelected();
    }
  }
});

uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert("Choose a PDF file first");
    return;
  }
  try {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
    currentDoc = await API.upload(file);
    currentPage = 0;
    piiSuggestions = [];
    updateDocInfo();
    await loadPage();
    await loadRedactions();
    canvas.clearSearchMatches();
    searchResults.textContent = "";
    exportStatus.innerHTML = "";
    piiResults.innerHTML = "";
    applyPiiBtn.classList.add("hidden");
  } catch (err) {
    alert(`Upload failed: ${err.message}`);
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload PDF";
  }
});

function updateDocInfo() {
  if (!currentDoc) return;
  docInfo.classList.remove("hidden");
  docInfo.innerHTML = `
    <strong>${currentDoc.original_filename}</strong><br>
    ${currentDoc.page_count} pages<br>
    Scale: ${currentDoc.render_scale}x
  `;

  if (currentDoc.is_scanned) {
    scannedBadge.classList.remove("hidden");
    ocrBtn.classList.remove("hidden");
  } else {
    scannedBadge.classList.add("hidden");
    ocrBtn.classList.add("hidden");
  }
}

async function loadPage() {
  if (!currentDoc) return;
  canvas.setRenderScale(currentDoc.render_scale);
  pageIndicator.textContent = `Page ${currentPage + 1} / ${currentDoc.page_count}`;
  await canvas.loadPageImage(API.pageImageUrl(currentDoc.id, currentPage));
}

async function loadRedactions() {
  if (!currentDoc) return;
  const all = await API.getRedactions(currentDoc.id);
  const pageRedactions = all.filter((r) => r.page_num === currentPage);
  canvas.setRedactions(pageRedactions);
}

prevPageBtn.addEventListener("click", async () => {
  if (!currentDoc || currentPage <= 0) return;
  currentPage -= 1;
  await loadPage();
  await loadRedactions();
  canvas.setSearchMatches(lastSearchMatches, currentPage);
});

nextPageBtn.addEventListener("click", async () => {
  if (!currentDoc || currentPage >= currentDoc.page_count - 1) return;
  currentPage += 1;
  await loadPage();
  await loadRedactions();
  canvas.setSearchMatches(lastSearchMatches, currentPage);
});

let lastSearchMatches = [];

searchBtn.addEventListener("click", async () => {
  if (!currentDoc) return;
  const query = searchInput.value.trim();
  if (!query) return;

  const result = await API.search(currentDoc.id, query);
  lastSearchMatches = result.matches;
  const onPage = result.matches.filter((m) => m.page_num === currentPage).length;
  searchResults.textContent = `${result.matches.length} match(es) total, ${onPage} on this page`;
  canvas.setSearchMatches(result.matches, currentPage);
});

bulkRedactBtn.addEventListener("click", async () => {
  if (!currentDoc) return;
  const query = searchInput.value.trim();
  if (!query) {
    alert("Enter a search term first");
    return;
  }
  if (!confirm(`Redact all matches for "${query}"?`)) return;

  const result = await API.bulkRedact(currentDoc.id, query);
  searchResults.textContent = `Created ${result.created} redaction(s)`;
  lastSearchMatches = [];
  canvas.clearSearchMatches();
  await loadRedactions();
});

exportBtn.addEventListener("click", async () => {
  if (!currentDoc) return;
  try {
    exportBtn.disabled = true;
    exportBtn.textContent = "Exporting...";
    const result = await API.export(currentDoc.id);
    const v = result.verification;
    let html = `<a href="${result.download_url}" download>Download ${result.filename}</a>`;
    if (v) {
      const cls = v.passed ? "pass" : "fail";
      html += `<br><span class="${cls}">Verification: ${v.passed ? "PASSED" : "FAILED"}</span>`;
      if (v.results.length) {
        html += "<ul>";
        for (const r of v.results) {
          html += `<li>${r.term}: ${r.found ? `FOUND on pages ${r.pages.join(", ")}` : "not found"}</li>`;
        }
        html += "</ul>";
      }
    }
    exportStatus.innerHTML = html;
  } catch (err) {
    exportStatus.innerHTML = `<span class="fail">Export failed: ${err.message}</span>`;
  } finally {
    exportBtn.disabled = false;
    exportBtn.textContent = "Export redacted PDF";
  }
});

ocrBtn.addEventListener("click", async () => {
  if (!currentDoc) return;
  try {
    ocrBtn.disabled = true;
    ocrBtn.textContent = "Running OCR...";
    const result = await API.runOcr(currentDoc.id);
    currentDoc = await API.getDocument(currentDoc.id);
    updateDocInfo();
    await loadPage();
    await loadRedactions();
    alert(`${result.message}\nTotal words: ${result.total_words}`);
  } catch (err) {
    alert(`OCR failed: ${err.message}`);
  } finally {
    ocrBtn.disabled = false;
    ocrBtn.textContent = "Run OCR";
  }
});

detectPiiBtn.addEventListener("click", async () => {
  if (!currentDoc) return;
  try {
    detectPiiBtn.disabled = true;
    detectPiiBtn.textContent = "Detecting...";
    const result = await API.detectPii(currentDoc.id);
    piiSuggestions = result.suggestions || [];

    if (result.message && !piiSuggestions.length) {
      piiResults.innerHTML = `<p class="hint">${result.message}</p>`;
      applyPiiBtn.classList.add("hidden");
      return;
    }

    renderPiiResults();
    applyPiiBtn.classList.remove("hidden");
  } catch (err) {
    piiResults.innerHTML = `<p class="hint">${err.message}</p>`;
  } finally {
    detectPiiBtn.disabled = false;
    detectPiiBtn.textContent = "Detect PII";
  }
});

function renderPiiResults() {
  piiResults.innerHTML = "";
  piiSuggestions.forEach((s, i) => {
    const div = document.createElement("div");
    div.className = "pii-item";
    div.innerHTML = `
      <input type="checkbox" id="pii-${i}" checked data-index="${i}">
      <label for="pii-${i}">
        <strong>${s.entity_type}</strong>: "${s.text}" (p.${s.page_num + 1}, ${(s.score * 100).toFixed(0)}%)
      </label>
    `;
    piiResults.appendChild(div);
  });
}

applyPiiBtn.addEventListener("click", async () => {
  if (!currentDoc || !piiSuggestions.length) return;
  const selected = [];
  piiResults.querySelectorAll("input[type=checkbox]:checked").forEach((cb) => {
    const idx = parseInt(cb.dataset.index, 10);
    selected.push(piiSuggestions[idx]);
  });
  if (!selected.length) {
    alert("Select at least one PII suggestion");
    return;
  }

  await API.applyPii(currentDoc.id, selected);
  await loadRedactions();
  alert(`Applied ${selected.length} PII redaction(s)`);
});
