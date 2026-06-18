/* Step 1: Organize files and pages. */

const organizeState = {
  pages: [],
  documents: [],
  selectedSlotIds: new Set(),
  canUndo: false,
  canRedo: false,
  dragSlotId: null,
};

async function loadOrganizeView() {
  if (!state.currentProjectId) return;
  showView("organize");
  updateStepBreadcrumb("organize", state.currentProject);
  await refreshOrganizeData();
}

async function refreshOrganizeData() {
  const [pagesResult, docsResult] = await Promise.all([
    API.getProjectPages(state.currentProjectId),
    API.listDocuments(state.currentProjectId),
  ]);
  organizeState.pages = pagesResult.pages;
  organizeState.canUndo = pagesResult.can_undo;
  organizeState.canRedo = pagesResult.can_redo;
  organizeState.documents = docsResult.documents;
  organizeState.selectedSlotIds = new Set(
    [...organizeState.selectedSlotIds].filter((id) =>
      organizeState.pages.some((p) => p.id === id)
    )
  );
  renderOrganizeDocs();
  renderOrganizeGrid();
  updateOrganizeToolbar();
}

function renderOrganizeDocs() {
  const container = document.getElementById("organize-doc-list");
  container.innerHTML = "";
  if (!organizeState.documents.length) {
    container.innerHTML = "<p class='hint'>No documents yet.</p>";
    return;
  }
  for (const doc of organizeState.documents) {
    const item = document.createElement("div");
    item.className = "doc-item";
    item.innerHTML = `
      <div class="doc-main">
        <div class="doc-name" title="${escapeHtml(doc.original_filename)}">${escapeHtml(doc.original_filename)}</div>
        <div class="doc-meta"><span>${doc.page_count} pages</span></div>
      </div>
    `;
    container.appendChild(item);
  }
}

function renderOrganizeGrid() {
  const grid = document.getElementById("organize-page-grid");
  grid.innerHTML = "";

  if (!organizeState.pages.length) {
    grid.innerHTML = "<p class='hint'>Add PDFs to start organizing pages.</p>";
    return;
  }

  for (const page of organizeState.pages) {
    const tile = document.createElement("div");
    tile.className = "organize-tile";
    tile.draggable = true;
    tile.dataset.slotId = String(page.id);
    if (organizeState.selectedSlotIds.has(page.id)) tile.classList.add("selected");

    tile.innerHTML = `
      <div class="organize-tile-check">
        <input type="checkbox" ${organizeState.selectedSlotIds.has(page.id) ? "checked" : ""}>
      </div>
      <img src="${page.thumbnail_url}" alt="Page ${page.slot_index + 1}" loading="lazy">
      <div class="organize-tile-label">
        <span class="page-num">p. ${page.slot_index + 1}</span>
        <span class="page-src" title="${escapeHtml(page.source_filename)}">${escapeHtml(page.source_filename)}</span>
      </div>
    `;

    tile.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) organizeState.selectedSlotIds.add(page.id);
      else organizeState.selectedSlotIds.delete(page.id);
      renderOrganizeGrid();
      updateOrganizeToolbar();
    });

    tile.addEventListener("dragstart", (e) => {
      organizeState.dragSlotId = page.id;
      tile.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(page.id));
    });
    tile.addEventListener("dragend", () => {
      organizeState.dragSlotId = null;
      tile.classList.remove("dragging");
      grid.querySelectorAll(".drop-target").forEach((el) => el.classList.remove("drop-target"));
    });
    tile.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      tile.classList.add("drop-target");
    });
    tile.addEventListener("dragleave", () => tile.classList.remove("drop-target"));
    tile.addEventListener("drop", async (e) => {
      e.preventDefault();
      tile.classList.remove("drop-target");
      const fromId = parseInt(e.dataTransfer.getData("text/plain"), 10);
      const toId = page.id;
      if (!fromId || fromId === toId) return;
      await reorderOrganizeSlots(fromId, toId);
    });

    grid.appendChild(tile);
  }
}

async function reorderOrganizeSlots(fromId, toId) {
  const ids = organizeState.pages.map((p) => p.id);
  const fromIdx = ids.indexOf(fromId);
  const toIdx = ids.indexOf(toId);
  if (fromIdx < 0 || toIdx < 0) return;
  ids.splice(fromIdx, 1);
  ids.splice(toIdx, 0, fromId);
  try {
    await API.reorderProjectPages(state.currentProjectId, ids);
    await refreshOrganizeData();
  } catch (err) {
    alert(err.message);
  }
}

function updateOrganizeToolbar() {
  document.getElementById("organize-undo-btn").disabled = !organizeState.canUndo;
  document.getElementById("organize-redo-btn").disabled = !organizeState.canRedo;
  document.getElementById("organize-delete-pages-btn").disabled =
    !organizeState.selectedSlotIds.size;
  document.getElementById("organize-continue-btn").disabled = !organizeState.pages.length;
  document.getElementById("organize-page-count").textContent = organizeState.pages.length
    ? `${organizeState.pages.length} page${organizeState.pages.length !== 1 ? "s" : ""}`
    : "";
  document.getElementById("organize-merge-btn").disabled = organizeState.documents.length < 2;
}

function initOrganize() {
  const fileInput = document.getElementById("organize-file-input");
  document.getElementById("organize-upload-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    if (!fileInput.files.length || !state.currentProjectId) return;
    try {
      const result = await API.uploadProjectDocuments(state.currentProjectId, fileInput.files);
      if (result.errors.length) alert(result.errors.join("\n"));
      await refreshOrganizeData();
      if (state.currentProject) {
        state.currentProject = await API.getProject(state.currentProjectId);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      fileInput.value = "";
    }
  });

  document.getElementById("organize-undo-btn").addEventListener("click", async () => {
    try {
      await API.organizeUndo(state.currentProjectId);
      await refreshOrganizeData();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("organize-redo-btn").addEventListener("click", async () => {
    try {
      await API.organizeRedo(state.currentProjectId);
      await refreshOrganizeData();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("organize-merge-btn").addEventListener("click", async () => {
    if (!confirm("Merge all documents in list order into one page sequence?")) return;
    try {
      await API.mergeProjectDocuments(state.currentProjectId);
      await refreshOrganizeData();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("organize-delete-pages-btn").addEventListener("click", async () => {
    if (!organizeState.selectedSlotIds.size) return;
    if (!confirm(`Delete ${organizeState.selectedSlotIds.size} selected page(s)?`)) return;
    try {
      await API.deleteProjectPages(state.currentProjectId, [...organizeState.selectedSlotIds]);
      organizeState.selectedSlotIds.clear();
      await refreshOrganizeData();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("organize-continue-btn").addEventListener("click", async () => {
    if (!organizeState.pages.length) return;
    if (
      !confirm(
        "Continue to redaction? This will finalize the page arrangement into a working document."
      )
    )
      return;
    try {
      const result = await API.advanceProject(state.currentProjectId);
      state.currentProject = result.project;
      Router.navigate("redact", state.currentProjectId, "redact");
    } catch (err) {
      alert(err.message);
    }
  });
}
