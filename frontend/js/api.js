const API = {
  async upload(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/documents", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getDocument(id) {
    const res = await fetch(`/api/documents/${id}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  pageImageUrl(id, pageNum) {
    return `/api/documents/${id}/pages/${pageNum}/image`;
  },

  async search(id, query) {
    const res = await fetch(`/api/documents/${id}/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getRedactions(id, page) {
    const url = page !== undefined
      ? `/api/documents/${id}/redactions?page=${page}`
      : `/api/documents/${id}/redactions`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async createRedaction(id, box) {
    const res = await fetch(`/api/documents/${id}/redactions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(box),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateRedaction(redactionId, box) {
    const res = await fetch(`/api/redactions/${redactionId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(box),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteRedaction(redactionId) {
    const res = await fetch(`/api/redactions/${redactionId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async bulkRedact(id, query) {
    const res = await fetch(`/api/documents/${id}/redactions/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async export(id) {
    const res = await fetch(`/api/documents/${id}/export`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async runOcr(id) {
    const res = await fetch(`/api/documents/${id}/ocr`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async detectPii(id) {
    const res = await fetch(`/api/documents/${id}/detect-pii`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async applyPii(id, suggestions) {
    const res = await fetch(`/api/documents/${id}/detect-pii/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestions }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};
