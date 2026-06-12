const STATUS_STYLES = {
  pending: { fill: "rgba(255, 193, 7, 0.30)", stroke: "rgba(255, 193, 7, 0.95)", dash: [] },
  needs_review: { fill: "rgba(255, 120, 40, 0.30)", stroke: "rgba(255, 120, 40, 0.95)", dash: [5, 3] },
  approved: { fill: "rgba(229, 83, 83, 0.35)", stroke: "rgba(229, 83, 83, 0.95)", dash: [] },
  applied: { fill: "rgba(10, 10, 10, 0.85)", stroke: "rgba(0, 0, 0, 1)", dash: [] },
  ignored: { fill: "rgba(150, 150, 150, 0.15)", stroke: "rgba(150, 150, 150, 0.6)", dash: [2, 3] },
};

const MANUAL_STYLE = { fill: "rgba(0, 180, 170, 0.30)", stroke: "rgba(0, 200, 190, 0.95)", dash: [] };
const SELECTED_STROKE = "#4f8cff";

class RedactionCanvas {
  constructor(pageCanvas, overlayCanvas, container) {
    this.pageCanvas = pageCanvas;
    this.overlayCanvas = overlayCanvas;
    this.container = container;
    this.pageCtx = pageCanvas.getContext("2d");
    this.overlayCtx = overlayCanvas.getContext("2d");

    this.renderScale = 2;
    this.zoom = 1;
    this.img = null;
    this.showOverlays = true;

    this.findings = [];
    this.words = [];
    this.searchMatches = [];
    this.selectedFindingId = null;
    this.mode = "select"; // select | draw | text

    this.isDragging = false;
    this.isDrawing = false;
    this.isResizing = false;
    this.isTextSelecting = false;
    this.resizeHandle = null;
    this.dragStart = null;
    this.drawStart = null;
    this.tempRect = null;
    this.textSelStart = null;
    this.textSelRect = null;

    this.onBoxDrawn = null; // (pdfRect, screenPoint)
    this.onFindingSelected = null; // (findingId | null)
    this.onManualUpdated = null; // (findingId, bbox)
    this.onTextSelected = null; // (text, screenPoint)

    this.overlayCanvas.addEventListener("mousedown", (e) => this.onMouseDown(e));
    this.overlayCanvas.addEventListener("mousemove", (e) => this.onMouseMove(e));
    this.overlayCanvas.addEventListener("mouseup", (e) => this.onMouseUp(e));
    this.overlayCanvas.addEventListener("mouseleave", (e) => this.onMouseUp(e));
  }

  setRenderScale(scale) {
    this.renderScale = scale;
  }

  setZoom(zoom) {
    this.zoom = Math.min(4, Math.max(0.25, zoom));
    this.redrawAll();
  }

  setMode(mode) {
    this.mode = mode;
    this.overlayCanvas.style.cursor =
      mode === "draw" ? "crosshair" : mode === "text" ? "text" : "default";
  }

  setFindings(findings) {
    this.findings = findings.map((f) => ({ ...f, rects: f.rects.map((r) => ({ ...r })) }));
    this.render();
  }

  setWords(words) {
    this.words = words || [];
  }

  setSearchMatches(matches) {
    this.searchMatches = matches || [];
    this.render();
  }

  setShowOverlays(show) {
    this.showOverlays = show;
    this.render();
  }

  async loadPageImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        this.img = img;
        this.redrawAll();
        resolve();
      };
      img.onerror = reject;
      img.src = url;
    });
  }

  redrawAll() {
    if (!this.img) return;
    const w = Math.round(this.img.width * this.zoom);
    const h = Math.round(this.img.height * this.zoom);
    this.pageCanvas.width = w;
    this.pageCanvas.height = h;
    this.overlayCanvas.width = w;
    this.overlayCanvas.height = h;
    this.container.style.width = `${w}px`;
    this.container.style.height = `${h}px`;
    this.pageCtx.drawImage(this.img, 0, 0, w, h);
    this.render();
  }

  get factor() {
    return this.renderScale * this.zoom;
  }

  pdfToScreen(rect) {
    const f = this.factor;
    return { x0: rect.x0 * f, y0: rect.y0 * f, x1: rect.x1 * f, y1: rect.y1 * f };
  }

  screenToPdf(x0, y0, x1, y1) {
    const f = this.factor;
    return { x0: x0 / f, y0: y0 / f, x1: x1 / f, y1: y1 / f };
  }

  normalizeRect(x0, y0, x1, y1) {
    return {
      x0: Math.min(x0, x1),
      y0: Math.min(y0, y1),
      x1: Math.max(x0, x1),
      y1: Math.max(y0, y1),
    };
  }

  getMousePos(e) {
    const rect = this.overlayCanvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  findFindingAt(x, y) {
    for (let i = this.findings.length - 1; i >= 0; i--) {
      const finding = this.findings[i];
      for (const rect of finding.rects) {
        const r = this.pdfToScreen(rect);
        if (x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1) return finding;
      }
    }
    return null;
  }

  getHandleAt(x, y, finding) {
    const r = this.pdfToScreen(finding);
    const size = 8;
    const handles = {
      nw: { x: r.x0, y: r.y0 },
      ne: { x: r.x1, y: r.y0 },
      sw: { x: r.x0, y: r.y1 },
      se: { x: r.x1, y: r.y1 },
    };
    for (const [name, pos] of Object.entries(handles)) {
      if (Math.abs(x - pos.x) <= size && Math.abs(y - pos.y) <= size) return name;
    }
    return null;
  }

  onMouseDown(e) {
    if (!this.showOverlays) return;
    const pos = this.getMousePos(e);

    if (this.mode === "draw") {
      this.isDrawing = true;
      this.drawStart = pos;
      this.tempRect = null;
      return;
    }

    if (this.mode === "text") {
      this.isTextSelecting = true;
      this.textSelStart = pos;
      this.textSelRect = null;
      return;
    }

    const hit = this.findFindingAt(pos.x, pos.y);
    if (hit) {
      this.selectedFindingId = hit.id;
      if (hit.source === "manual" && hit.status !== "applied") {
        const handle = this.getHandleAt(pos.x, pos.y, hit);
        if (handle) {
          this.isResizing = true;
          this.resizeHandle = handle;
        } else {
          this.isDragging = true;
        }
        this.dragStart = { ...pos, rect: this.pdfToScreen(hit) };
      }
      this.render();
      if (this.onFindingSelected) this.onFindingSelected(hit.id);
      return;
    }

    this.selectedFindingId = null;
    this.render();
    if (this.onFindingSelected) this.onFindingSelected(null);
  }

  onMouseMove(e) {
    const pos = this.getMousePos(e);

    if (this.isDrawing && this.drawStart) {
      this.tempRect = this.normalizeRect(this.drawStart.x, this.drawStart.y, pos.x, pos.y);
      this.render();
      return;
    }

    if (this.isTextSelecting && this.textSelStart) {
      this.textSelRect = this.normalizeRect(this.textSelStart.x, this.textSelStart.y, pos.x, pos.y);
      this.render();
      return;
    }

    if (!this.selectedFindingId) return;
    const finding = this.findings.find((f) => f.id === this.selectedFindingId);
    if (!finding || finding.source !== "manual") return;

    if (this.isDragging && this.dragStart) {
      const dx = pos.x - this.dragStart.x;
      const dy = pos.y - this.dragStart.y;
      const moved = this.normalizeRect(
        this.dragStart.rect.x0 + dx,
        this.dragStart.rect.y0 + dy,
        this.dragStart.rect.x1 + dx,
        this.dragStart.rect.y1 + dy
      );
      const pdf = this.screenToPdf(moved.x0, moved.y0, moved.x1, moved.y1);
      Object.assign(finding, pdf);
      finding.rects = [{ ...pdf }];
      this.render();
      return;
    }

    if (this.isResizing && this.resizeHandle) {
      const screen = this.pdfToScreen(finding);
      let { x0, y0, x1, y1 } = screen;
      if (this.resizeHandle.includes("n")) y0 = pos.y;
      if (this.resizeHandle.includes("s")) y1 = pos.y;
      if (this.resizeHandle.includes("w")) x0 = pos.x;
      if (this.resizeHandle.includes("e")) x1 = pos.x;
      const norm = this.normalizeRect(x0, y0, x1, y1);
      const pdf = this.screenToPdf(norm.x0, norm.y0, norm.x1, norm.y1);
      Object.assign(finding, pdf);
      finding.rects = [{ ...pdf }];
      this.render();
    }
  }

  _selectedWords() {
    if (!this.textSelRect) return [];
    const sel = this.screenToPdf(
      this.textSelRect.x0,
      this.textSelRect.y0,
      this.textSelRect.x1,
      this.textSelRect.y1
    );
    return this.words.filter(
      (w) => w.x1 > sel.x0 && w.x0 < sel.x1 && w.y1 > sel.y0 && w.y0 < sel.y1
    );
  }

  async onMouseUp(e) {
    if (this.isDrawing && this.drawStart && this.tempRect) {
      const { x0, y0, x1, y1 } = this.tempRect;
      if (Math.abs(x1 - x0) > 4 && Math.abs(y1 - y0) > 4) {
        const pdf = this.screenToPdf(x0, y0, x1, y1);
        if (this.onBoxDrawn) {
          this.onBoxDrawn(pdf, { x: e.clientX, y: e.clientY });
        }
      }
    }

    if (this.isTextSelecting && this.textSelRect) {
      const words = this._selectedWords();
      if (words.length && this.onTextSelected) {
        const text = words.map((w) => w.text).join(" ");
        this.onTextSelected(text, { x: e.clientX, y: e.clientY });
      }
    }

    if ((this.isDragging || this.isResizing) && this.selectedFindingId && this.onManualUpdated) {
      const finding = this.findings.find((f) => f.id === this.selectedFindingId);
      if (finding) {
        await this.onManualUpdated(finding.id, {
          x0: finding.x0,
          y0: finding.y0,
          x1: finding.x1,
          y1: finding.y1,
        });
      }
    }

    this.isDragging = false;
    this.isResizing = false;
    this.isDrawing = false;
    this.isTextSelecting = false;
    this.resizeHandle = null;
    this.dragStart = null;
    this.drawStart = null;
    this.tempRect = null;
    this.textSelStart = null;
    this.textSelRect = null;
    this.render();
  }

  styleFor(finding) {
    if (finding.status === "applied") return STATUS_STYLES.applied;
    if (finding.source === "manual") return MANUAL_STYLE;
    return STATUS_STYLES[finding.status] || STATUS_STYLES.pending;
  }

  render() {
    const ctx = this.overlayCtx;
    ctx.clearRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);
    if (!this.showOverlays) return;

    for (const match of this.searchMatches) {
      const r = this.pdfToScreen(match);
      ctx.fillStyle = "rgba(120, 80, 255, 0.30)";
      ctx.strokeStyle = "rgba(120, 80, 255, 0.9)";
      ctx.lineWidth = 1;
      ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
    }

    for (const finding of this.findings) {
      const style = this.styleFor(finding);
      const selected = finding.id === this.selectedFindingId;
      for (const rect of finding.rects) {
        const r = this.pdfToScreen(rect);
        ctx.fillStyle = style.fill;
        ctx.strokeStyle = selected ? SELECTED_STROKE : style.stroke;
        ctx.lineWidth = selected ? 2.5 : 1.25;
        ctx.setLineDash(selected ? [] : style.dash);
        ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
        ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
        ctx.setLineDash([]);
      }
      if (selected && finding.source === "manual" && finding.status !== "applied") {
        this.drawHandles(this.pdfToScreen(finding));
      }
    }

    if (this.tempRect) {
      const r = this.tempRect;
      ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
      ctx.strokeStyle = SELECTED_STROKE;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      ctx.setLineDash([]);
    }

    if (this.textSelRect) {
      for (const word of this._selectedWords()) {
        const r = this.pdfToScreen(word);
        ctx.fillStyle = "rgba(79, 140, 255, 0.35)";
        ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      }
      const r = this.textSelRect;
      ctx.strokeStyle = "rgba(79, 140, 255, 0.6)";
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      ctx.setLineDash([]);
    }
  }

  drawHandles(r) {
    const ctx = this.overlayCtx;
    const size = 4;
    const points = [
      [r.x0, r.y0],
      [r.x1, r.y0],
      [r.x0, r.y1],
      [r.x1, r.y1],
    ];
    ctx.fillStyle = SELECTED_STROKE;
    for (const [x, y] of points) {
      ctx.fillRect(x - size, y - size, size * 2, size * 2);
    }
  }

  selectById(id) {
    this.selectedFindingId = id;
    this.render();
  }
}
