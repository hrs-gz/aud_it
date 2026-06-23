async function _json(res) {
  if (!res.ok) {
    let detail = await res.text();
    try {
      const parsed = JSON.parse(detail);
      if (parsed.detail) detail = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch (_) { /* raw text */ }
    throw new Error(detail);
  }
  return res.json();
}

function _post(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(_json);
}

const API = {
  // --- documents ---
  async upload(files, projectId = null) {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    const url = projectId
      ? `/api/documents?project_id=${encodeURIComponent(projectId)}`
      : "/api/documents";
    return _json(await fetch(url, { method: "POST", body: form }));
  },

  async listDocuments(projectId = null) {
    const url = projectId
      ? `/api/documents?project_id=${encodeURIComponent(projectId)}`
      : "/api/documents";
    return _json(await fetch(url));
  },

  async getDocument(id) {
    return _json(await fetch(`/api/documents/${id}`));
  },

  async deleteDocument(id) {
    return _json(await fetch(`/api/documents/${id}`, { method: "DELETE" }));
  },

  pageImageUrl(id, pageNum, version = "original") {
    return `/api/documents/${id}/pages/${pageNum}/image?version=${version}`;
  },

  async getWords(id, pageNum) {
    return _json(await fetch(`/api/documents/${id}/pages/${pageNum}/words`));
  },

  async search(id, query) {
    return _json(await fetch(`/api/documents/${id}/search?q=${encodeURIComponent(query)}`));
  },

  async runOcr(id) {
    return _json(await fetch(`/api/documents/${id}/ocr`, { method: "POST" }));
  },

  // --- findings ---
  async getFindings({ documentIds, page, entityType, status, source, minConfidence } = {}) {
    const params = new URLSearchParams();
    for (const id of documentIds || []) params.append("document_ids", id);
    if (page !== undefined && page !== null) params.set("page", page);
    if (entityType) params.set("entity_type", entityType);
    for (const s of status || []) params.append("status", s);
    if (source) params.set("source", source);
    if (minConfidence != null) params.set("min_confidence", minConfidence);
    return _json(await fetch(`/api/findings?${params}`));
  },

  async revealFinding(id) {
    return _json(await fetch(`/api/findings/${id}/value`));
  },

  createManualFinding(docId, payload) {
    return _post(`/api/documents/${docId}/findings`, payload);
  },

  async updateFinding(id, patch) {
    return _json(
      await fetch(`/api/findings/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      })
    );
  },

  async deleteFinding(id) {
    return _json(await fetch(`/api/findings/${id}`, { method: "DELETE" }));
  },

  bulkFindings(action, filter) {
    return _post("/api/findings/bulk", { action, filter });
  },

  searchFindings(query, documentIds) {
    return _post("/api/findings/search", { query, document_ids: documentIds });
  },

  // --- batch pipeline ---
  batchDetect(documentIds, entities, scoreThreshold) {
    return _post("/api/batch/detect", {
      document_ids: documentIds,
      entities,
      score_threshold: scoreThreshold,
      auto_ocr: true,
    });
  },

  batchApply(documentIds) {
    return _post("/api/batch/apply", { document_ids: documentIds });
  },

  batchVerify(documentIds) {
    return _post("/api/batch/verify", { document_ids: documentIds });
  },

  batchExport(documentIds, allowUnverified) {
    return _post("/api/batch/export", {
      document_ids: documentIds,
      allow_unverified: allowUnverified,
    });
  },

  async getVerification(docId) {
    return _json(await fetch(`/api/documents/${docId}/verification`));
  },

  // --- recognizers & rules ---
  async getPresidioStatus() {
    return _json(await fetch("/api/presidio/status"));
  },

  async getRecognizers() {
    return _json(await fetch("/api/presidio/recognizers"));
  },

  async getRules() {
    return _json(await fetch("/api/rules"));
  },

  createRule(payload) {
    return _post("/api/rules", payload);
  },

  async updateRule(id, patch) {
    return _json(
      await fetch(`/api/rules/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      })
    );
  },

  async deleteRule(id) {
    return _json(await fetch(`/api/rules/${id}`, { method: "DELETE" }));
  },

  suggestPattern(examples) {
    return _post("/api/rules/suggest", { examples });
  },

  testPattern(pattern, documentIds) {
    return _post("/api/rules/test", { pattern, document_ids: documentIds });
  },

  // --- projects ---
  async listProjects() {
    return _json(await fetch("/api/projects"));
  },

  async createProject(name = "Untitled project") {
    return _post("/api/projects", { name });
  },

  async getProject(id) {
    return _json(await fetch(`/api/projects/${id}`));
  },

  async updateProject(id, patch) {
    return _json(
      await fetch(`/api/projects/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      })
    );
  },

  async deleteProject(id) {
    return _json(await fetch(`/api/projects/${id}`, { method: "DELETE" }));
  },

  async hardReset() {
    return _post("/api/admin/hard-reset", {});
  },

  async uploadProjectDocuments(projectId, files) {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return _json(await fetch(`/api/projects/${projectId}/documents`, { method: "POST", body: form }));
  },

  async getProjectPages(projectId) {
    return _json(await fetch(`/api/projects/${projectId}/pages`));
  },

  async reorderProjectPages(projectId, slotIds) {
    return _json(
      await fetch(`/api/projects/${projectId}/pages/reorder`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot_ids: slotIds }),
      })
    );
  },

  async deleteProjectPages(projectId, slotIds) {
    return _json(
      await fetch(`/api/projects/${projectId}/pages/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot_ids: slotIds }),
      })
    );
  },

  mergeProjectDocuments(projectId) {
    return _post(`/api/projects/${projectId}/merge-documents`, {});
  },

  organizeUndo(projectId) {
    return _post(`/api/projects/${projectId}/organize/undo`, {});
  },

  organizeRedo(projectId) {
    return _post(`/api/projects/${projectId}/organize/redo`, {});
  },

  advanceProject(projectId) {
    return _post(`/api/projects/${projectId}/advance`, {});
  },
};
