class RedactionCanvas {
  constructor(pageCanvas, overlayCanvas, container) {
    this.pageCanvas = pageCanvas;
    this.overlayCanvas = overlayCanvas;
    this.container = container;
    this.pageCtx = pageCanvas.getContext("2d");
    this.overlayCtx = overlayCanvas.getContext("2d");

    this.renderScale = 2;
    this.redactions = [];
    this.searchMatches = [];
    this.selectedId = null;
    this.mode = "select";

    this.isDragging = false;
    this.isDrawing = false;
    this.isResizing = false;
    this.resizeHandle = null;
    this.dragStart = null;
    this.drawStart = null;
    this.tempRect = null;

    this.onRedactionCreated = null;
    this.onRedactionUpdated = null;
    this.onRedactionDeleted = null;

    this.overlayCanvas.addEventListener("mousedown", (e) => this.onMouseDown(e));
    this.overlayCanvas.addEventListener("mousemove", (e) => this.onMouseMove(e));
    this.overlayCanvas.addEventListener("mouseup", (e) => this.onMouseUp(e));
    this.overlayCanvas.addEventListener("mouseleave", (e) => this.onMouseUp(e));
  }

  setRenderScale(scale) {
    this.renderScale = scale;
  }

  setMode(mode) {
    this.mode = mode;
    this.overlayCanvas.style.cursor =
      mode === "draw" ? "crosshair" : mode === "delete" ? "not-allowed" : "default";
  }

  setRedactions(redactions) {
    this.redactions = redactions.map((r) => ({ ...r }));
    this.selectedId = null;
    this.render();
  }

  setSearchMatches(matches, pageNum) {
    this.searchMatches = matches.filter((m) => m.page_num === pageNum);
    this.render();
  }

  clearSearchMatches() {
    this.searchMatches = [];
    this.render();
  }

  async loadPageImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        this.pageCanvas.width = img.width;
        this.pageCanvas.height = img.height;
        this.overlayCanvas.width = img.width;
        this.overlayCanvas.height = img.height;
        this.container.style.width = `${img.width}px`;
        this.container.style.height = `${img.height}px`;
        this.pageCtx.drawImage(img, 0, 0);
        this.render();
        resolve();
      };
      img.onerror = reject;
      img.src = url;
    });
  }

  pdfToScreen(rect) {
    return {
      x0: rect.x0 * this.renderScale,
      y0: rect.y0 * this.renderScale,
      x1: rect.x1 * this.renderScale,
      y1: rect.y1 * this.renderScale,
    };
  }

  screenToPdf(x0, y0, x1, y1) {
    return {
      x0: x0 / this.renderScale,
      y0: y0 / this.renderScale,
      x1: x1 / this.renderScale,
      y1: y1 / this.renderScale,
    };
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
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  }

  findRedactionAt(x, y) {
    for (let i = this.redactions.length - 1; i >= 0; i--) {
      const r = this.pdfToScreen(this.redactions[i]);
      if (x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1) {
        return this.redactions[i];
      }
    }
    return null;
  }

  getHandleAt(x, y, redaction) {
    const r = this.pdfToScreen(redaction);
    const size = 8;
    const handles = {
      nw: { x: r.x0, y: r.y0 },
      ne: { x: r.x1, y: r.y0 },
      sw: { x: r.x0, y: r.y1 },
      se: { x: r.x1, y: r.y1 },
    };
    for (const [name, pos] of Object.entries(handles)) {
      if (Math.abs(x - pos.x) <= size && Math.abs(y - pos.y) <= size) {
        return name;
      }
    }
    return null;
  }

  onMouseDown(e) {
    const pos = this.getMousePos(e);

    if (this.mode === "draw") {
      this.isDrawing = true;
      this.drawStart = pos;
      this.tempRect = null;
      return;
    }

    if (this.mode === "delete") {
      const hit = this.findRedactionAt(pos.x, pos.y);
      if (hit && this.onRedactionDeleted) {
        this.onRedactionDeleted(hit.id);
      }
      return;
    }

    const selected = this.findRedactionAt(pos.x, pos.y);
    if (selected) {
      this.selectedId = selected.id;
      const handle = this.getHandleAt(pos.x, pos.y, selected);
      if (handle) {
        this.isResizing = true;
        this.resizeHandle = handle;
      } else {
        this.isDragging = true;
      }
      this.dragStart = { ...pos, rect: this.pdfToScreen(selected) };
      this.render();
      return;
    }

    this.selectedId = null;
    this.render();
  }

  onMouseMove(e) {
    const pos = this.getMousePos(e);

    if (this.isDrawing && this.drawStart) {
      const rect = this.normalizeRect(this.drawStart.x, this.drawStart.y, pos.x, pos.y);
      this.tempRect = rect;
      this.render();
      return;
    }

    if (!this.selectedId) return;
    const redaction = this.redactions.find((r) => r.id === this.selectedId);
    if (!redaction) return;

    const screen = this.pdfToScreen(redaction);

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
      Object.assign(redaction, pdf);
      this.render();
      return;
    }

    if (this.isResizing && this.resizeHandle) {
      let { x0, y0, x1, y1 } = screen;
      if (this.resizeHandle.includes("n")) y0 = pos.y;
      if (this.resizeHandle.includes("s")) y1 = pos.y;
      if (this.resizeHandle.includes("w")) x0 = pos.x;
      if (this.resizeHandle.includes("e")) x1 = pos.x;
      const norm = this.normalizeRect(x0, y0, x1, y1);
      const pdf = this.screenToPdf(norm.x0, norm.y0, norm.x1, norm.y1);
      Object.assign(redaction, pdf);
      this.render();
    }
  }

  async onMouseUp() {
    if (this.isDrawing && this.drawStart && this.tempRect) {
      const { x0, y0, x1, y1 } = this.tempRect;
      if (Math.abs(x1 - x0) > 4 && Math.abs(y1 - y0) > 4) {
        const pdf = this.screenToPdf(x0, y0, x1, y1);
        if (this.onRedactionCreated) {
          await this.onRedactionCreated(pdf);
        }
      }
    }

    if ((this.isDragging || this.isResizing) && this.selectedId && this.onRedactionUpdated) {
      const redaction = this.redactions.find((r) => r.id === this.selectedId);
      if (redaction) {
        await this.onRedactionUpdated(redaction.id, {
          x0: redaction.x0,
          y0: redaction.y0,
          x1: redaction.x1,
          y1: redaction.y1,
        });
      }
    }

    this.isDragging = false;
    this.isResizing = false;
    this.isDrawing = false;
    this.resizeHandle = null;
    this.dragStart = null;
    this.drawStart = null;
    this.tempRect = null;
    this.render();
  }

  render() {
    const ctx = this.overlayCtx;
    ctx.clearRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);

    for (const match of this.searchMatches) {
      const r = this.pdfToScreen(match);
      ctx.fillStyle = "rgba(255, 200, 0, 0.35)";
      ctx.strokeStyle = "rgba(255, 180, 0, 0.9)";
      ctx.lineWidth = 1;
      ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
    }

    for (const redaction of this.redactions) {
      const r = this.pdfToScreen(redaction);
      const selected = redaction.id === this.selectedId;
      ctx.fillStyle = selected ? "rgba(0, 0, 0, 0.55)" : "rgba(0, 0, 0, 0.4)";
      ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
      ctx.strokeStyle = selected ? "#4f8cff" : "#333";
      ctx.lineWidth = selected ? 2 : 1;
      ctx.strokeRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);

      if (selected) {
        this.drawHandles(r);
      }
    }

    if (this.tempRect) {
      const r = this.tempRect;
      ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
      ctx.strokeStyle = "#4f8cff";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.fillRect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0);
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
    ctx.fillStyle = "#4f8cff";
    for (const [x, y] of points) {
      ctx.fillRect(x - size, y - size, size * 2, size * 2);
    }
  }

  selectById(id) {
    this.selectedId = id;
    this.render();
  }

  deleteSelected() {
    if (this.selectedId && this.onRedactionDeleted) {
      this.onRedactionDeleted(this.selectedId);
      this.selectedId = null;
    }
  }
}
