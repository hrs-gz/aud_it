# AGENTS.md

## Cursor Cloud specific instructions

`aud_it` is a single local-first app: a FastAPI backend (`backend/main.py`) that also
serves the static vanilla-JS frontend (`frontend/`). There is no separate frontend
build or dev server, and no Node tooling — opening the backend URL serves the UI.

### Environment
- Python dependencies live in a virtualenv at `.venv` (created during setup). Activate
  with `source .venv/bin/activate`, or call binaries directly (e.g. `.venv/bin/uvicorn`).
- The spaCy model `en_core_web_lg` (~400 MB) is required for PII detection and is
  installed into `.venv`. Without it, the app boots but detection endpoints fail.
- `pytest` is NOT listed in `requirements.txt`; it is installed separately as a dev tool.
- System binaries `tesseract` and `ocrmypdf` are installed via apt and are only needed
  for OCR of scanned/image PDFs (optional). Text-based PDFs work without them.

### Run the app (development)
```bash
.venv/bin/uvicorn backend.main:app --port 8000   # add --reload for hot reload
```
Then open http://localhost:8000 — the backend serves the full UI at `/`.
Core flow in the UI: Import PDF → Detect → "Redact all high-confidence" (approve) →
"Apply redactions". True redactions are applied to working copies; originals are never
modified. Storage dirs (`storage/`, `data/`) are auto-created on startup and git-ignored.

### Tests
```bash
.venv/bin/pytest
```
Tests isolate storage/DB to a temp dir via `AUD_IT_*` env vars (see `tests/conftest.py`)
and skip gracefully when Presidio/Tesseract are unavailable.

Known: `tests/test_new_recognizers.py::test_a_number_detected_with_context` fails with
the currently-pinned Presidio (the match span includes a trailing space). This is a
library-version sensitivity, not an environment problem.

### Lint / build
There is no linter config and no build step (Python runs directly; frontend is static).
