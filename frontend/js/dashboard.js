/* Project dashboard: list, create, open, rename, delete. */

let focusProjectIdAfterRender = null;

async function refreshProjectList() {
  const grid = document.getElementById("project-grid");
  try {
    const result = await API.listProjects();
    state.projects = result.projects;
    renderProjectGrid();
  } catch (err) {
    grid.innerHTML = `<p class="hint fail">${err.message}</p>`;
  }
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function stepLabel(step) {
  return { organize: "Organize", redact: "Redact", export: "Export" }[step] || step;
}

function renderProjectGrid() {
  const grid = document.getElementById("project-grid");
  grid.innerHTML = "";

  if (!state.projects.length) {
    grid.innerHTML =
      '<p class="hint">No projects yet. Create one to start organizing and redacting PDFs.</p>';
    return;
  }

  for (const project of state.projects) {
    const card = document.createElement("div");
    card.className = "project-card";
    card.innerHTML = `
      <div class="project-card-head">
        <input type="text" class="project-name-input" value="${escapeHtml(project.name)}" data-id="${project.id}">
        <span class="step-badge">${stepLabel(project.step)}</span>
      </div>
      <div class="project-card-meta">
        <span>${project.document_count} doc${project.document_count !== 1 ? "s" : ""}</span>
        <span>${project.page_count} page${project.page_count !== 1 ? "s" : ""}</span>
        <span>Updated ${formatDate(project.updated_at)}</span>
      </div>
      <div class="project-card-actions">
        <button class="btn small primary open-project" data-id="${project.id}" data-step="${project.step}">Open</button>
        <button class="btn small danger delete-project" data-id="${project.id}">Delete</button>
      </div>
    `;

    const nameInput = card.querySelector(".project-name-input");
    nameInput.addEventListener("change", async () => {
      const name = nameInput.value.trim() || "Untitled project";
      try {
        await API.updateProject(project.id, { name });
        project.name = name;
      } catch (err) {
        alert(err.message);
        nameInput.value = project.name;
      }
    });
    nameInput.addEventListener("click", (e) => e.stopPropagation());

    card.querySelector(".open-project").addEventListener("click", () => {
      openProject(project.id, project.step);
    });
    card.querySelector(".delete-project").addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm(`Delete "${project.name}" and all its documents?`)) return;
      try {
        await API.deleteProject(project.id);
        await refreshProjectList();
      } catch (err) {
        alert(err.message);
      }
    });

    grid.appendChild(card);

    if (focusProjectIdAfterRender === project.id) {
      nameInput.focus();
      nameInput.select();
      focusProjectIdAfterRender = null;
    }
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

const newProjectModal = document.getElementById("new-project-modal");
const newProjectNameInput = document.getElementById("new-project-name");

function openNewProjectModal() {
  newProjectNameInput.value = "Untitled project";
  newProjectModal.classList.remove("hidden");
  newProjectNameInput.focus();
  newProjectNameInput.select();
}

function closeNewProjectModal() {
  newProjectModal.classList.add("hidden");
}

async function submitNewProject() {
  const name = newProjectNameInput.value.trim() || "Untitled project";
  try {
    const project = await API.createProject(name);
    closeNewProjectModal();
    focusProjectIdAfterRender = project.id;
    await refreshProjectList();
  } catch (err) {
    alert(err.message);
  }
}

async function openProject(projectId, step) {
  try {
    state.currentProject = await API.getProject(projectId);
    state.currentProjectId = projectId;
    const targetStep = step || state.currentProject.step || "organize";
    Router.navigate(targetStep, projectId, targetStep);
  } catch (err) {
    alert(err.message);
  }
}

async function loadDashboardView() {
  state.currentProjectId = null;
  state.currentProject = null;
  clearProjectSession();
  showView("dashboard");
  await refreshProjectList();
}

function initDashboard() {
  document.getElementById("new-project-btn").addEventListener("click", openNewProjectModal);
  document.getElementById("new-project-create-btn").addEventListener("click", submitNewProject);
  document.getElementById("new-project-cancel-btn").addEventListener("click", closeNewProjectModal);
  document.getElementById("new-project-modal-close").addEventListener("click", closeNewProjectModal);
  newProjectModal.addEventListener("click", (e) => {
    if (e.target === newProjectModal) closeNewProjectModal();
  });
  newProjectNameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitNewProject();
    if (e.key === "Escape") closeNewProjectModal();
  });

  initHardClearModal();
}

const hardClearModal = document.getElementById("hard-clear-modal");
const hardClearConfirmInput = document.getElementById("hard-clear-confirm");
const hardClearSubmitBtn = document.getElementById("hard-clear-submit-btn");

function openHardClearModal() {
  const projectCount = state.projects.length;
  const docCount = state.projects.reduce((n, p) => n + (p.document_count || 0), 0);
  document.getElementById("hard-clear-summary").textContent =
    `${projectCount} project${projectCount !== 1 ? "s" : ""}, ${docCount} document${docCount !== 1 ? "s" : ""} will be removed.`;
  hardClearConfirmInput.value = "";
  hardClearSubmitBtn.disabled = true;
  hardClearModal.classList.remove("hidden");
  hardClearConfirmInput.focus();
}

function closeHardClearModal() {
  hardClearModal.classList.add("hidden");
}

async function submitHardClear() {
  if (hardClearConfirmInput.value.trim() !== "DELETE ALL") return;
  try {
    await API.hardReset();
    closeHardClearModal();
    await loadDashboardView();
  } catch (err) {
    alert(err.message);
  }
}

function initHardClearModal() {
  document.getElementById("hard-clear-btn").addEventListener("click", openHardClearModal);
  document.getElementById("hard-clear-cancel-btn").addEventListener("click", closeHardClearModal);
  document.getElementById("hard-clear-modal-close").addEventListener("click", closeHardClearModal);
  hardClearModal.addEventListener("click", (e) => {
    if (e.target === hardClearModal) closeHardClearModal();
  });
  hardClearConfirmInput.addEventListener("input", () => {
    hardClearSubmitBtn.disabled = hardClearConfirmInput.value.trim() !== "DELETE ALL";
  });
  hardClearConfirmInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !hardClearSubmitBtn.disabled) submitHardClear();
    if (e.key === "Escape") closeHardClearModal();
  });
  hardClearSubmitBtn.addEventListener("click", submitHardClear);
}
