/* Hash-based view router for project workflow. */

const Router = {
  parse() {
    const hash = location.hash.replace(/^#/, "") || "/";
    const parts = hash.split("/").filter(Boolean);
    if (!parts.length || parts[0] !== "project") {
      return { view: "dashboard", projectId: null, step: null };
    }
    const projectId = parts[1] || null;
    const step = parts[2] || "organize";
    if (!projectId) return { view: "dashboard", projectId: null, step: null };
    const validSteps = ["organize", "redact", "export"];
    return {
      view: validSteps.includes(step) ? step : "organize",
      projectId,
      step: validSteps.includes(step) ? step : "organize",
    };
  },

  navigate(view, projectId = null, step = null) {
    if (view === "dashboard" || !projectId) {
      location.hash = "#/";
      return;
    }
    const s = step || view;
    location.hash = `#/project/${projectId}/${s}`;
  },

  onRoute(handler) {
    window.addEventListener("hashchange", () => handler(this.parse()));
    handler(this.parse());
  },
};

function showView(viewName) {
  for (const el of document.querySelectorAll(".view")) {
    el.classList.add("hidden");
  }
  const map = {
    dashboard: "view-dashboard",
    organize: "view-organize",
    redact: "view-redact",
    export: "view-export",
  };
  const id = map[viewName];
  if (id) document.getElementById(id).classList.remove("hidden");

  const breadcrumb = document.getElementById("step-breadcrumb");
  const projectTitle = document.getElementById("project-title");
  const closeBtn = document.getElementById("close-project-btn");
  const inProject = viewName !== "dashboard";

  breadcrumb.classList.toggle("hidden", !inProject);
  projectTitle.classList.toggle("hidden", !inProject);
  closeBtn.classList.toggle("hidden", !inProject);
}

function updateStepBreadcrumb(currentStep, project) {
  const breadcrumb = document.getElementById("step-breadcrumb");
  if (!breadcrumb || !project) return;

  const order = ["organize", "redact", "export"];
  const currentIdx = order.indexOf(currentStep);
  const savedIdx = order.indexOf(project.step);

  breadcrumb.querySelectorAll(".step-link").forEach((btn) => {
    const step = btn.dataset.step;
    const stepIdx = order.indexOf(step);
    btn.classList.remove("active", "done", "disabled");
    if (step === currentStep) btn.classList.add("active");
    else if (stepIdx < savedIdx) btn.classList.add("done");
    else if (stepIdx > savedIdx) btn.classList.add("disabled");
  });

  if (state.currentProject) {
    document.getElementById("project-title").textContent = state.currentProject.name;
  }
}

function initRouter() {
  document.getElementById("close-project-btn").addEventListener("click", () => {
    Router.navigate("dashboard");
  });

  document.getElementById("step-breadcrumb").addEventListener("click", (e) => {
    const btn = e.target.closest(".step-link");
    if (!btn || btn.classList.contains("disabled") || !state.currentProjectId) return;
    const step = btn.dataset.step;
    const order = ["organize", "redact", "export"];
    const savedIdx = order.indexOf(state.currentProject?.step || "organize");
    const targetIdx = order.indexOf(step);
    if (targetIdx <= savedIdx) {
      Router.navigate(step, state.currentProjectId, step);
    }
  });
}
