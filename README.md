# aud_it

Local-first PDF redaction app. Import PDFs in batch, detect PII, review every finding, apply true redactions, verify nothing leaked, and export with audit reports. No login, no cloud, no network calls.

## Workflow

`New project → Organize files → Redact → Review & Export`

Within a project:

1. **Organize** — add PDFs, rearrange page thumbnails, delete pages, merge documents, undo/redo
2. **Redact** — detect PII, review findings, apply redactions, verify
3. **Export** — final preview, redaction report, export PDFs and project ZIP

Findings move through a staged lifecycle — nothing is redacted until you apply:

`pending / needs_review → approved → applied → verified → exported` (or `ignored`)

The dashboard at `/` lists projects. Open a project to continue at its saved step (`#/project/{id}/organize`, `redact`, or `export`).

## Features

- Batch import; per-document status (OCR / detecting / applying / verifying / error)
- PII detection with Microsoft Presidio + spaCy (all local): SSN, phone, email, names, locations, organizations, A-numbers, DOB, MRN, account and case IDs
- Custom rules: low-code pattern builder (examples → suggested regex), advanced regex editor, test-on-documents, auto-approve or mark-for-review
- Three-panel review UI: document/page sidebar, zoomable viewer with status-colored overlays and original ↔ redacted toggle, review pane with Page/PII views, masked values with explicit reveal, filters, and bulk actions
- Manual redaction boxes (draw on page, apply to all pages) and text-selection → find similar / create rule
- OCR for scanned PDFs: OCRmyPDF preferred, PyMuPDF + Tesseract fallback that produces a real text layer; per-page failure reporting
- True redaction via PyMuPDF `apply_redactions` — text is removed, never just covered
- Verification pass: search test, residual PII sweep, metadata stripped, annotations flattened, no text under boxes, no unresolved approvals; failing docs block export (with explicit "export anyway")
- Export: per-document redacted PDFs and batch ZIP with `audit_report.json`, `redaction_summary.csv`, `verification_report.json` (counts and masked values only — no sensitive snippets)

## Privacy guarantees

- Originals are never modified; OCR and redactions go to a working copy (`storage/work/`)
- Finding values are masked in API responses; reveal is an explicit per-finding request
- No document text in logs; no network calls (Presidio's tldextract is pinned to its offline snapshot)

## Requirements

- Python 3.11+
- [Tesseract](https://github.com/tesseract-ocr/tesseract) (for OCR): `brew install tesseract`
- [OCRmyPDF](https://ocrmypdf.readthedocs.io/) (optional, preferred for scanned PDFs): `brew install ocrmypdf`

For Presidio PII detection:

```bash
python -m spacy download en_core_web_lg
```

## Setup

```bash
cd ~/Projects/aud_it
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
uvicorn backend.main:app --port 8000
```

Open http://localhost:8000

## Tests

```bash
pytest
```

Uses the synthetic corpus in `tests/redaction_test_pdfs/` (see `README_manifest.json`), including the intentionally unsafe black-box-overlay PDF.

### Database

SQLite foreign key enforcement is enabled on every connection (`PRAGMA foreign_keys=ON`). During the organize step, `ProjectPage` slots reference source documents via a non-null FK; always remove slots before deleting documents (see `delete_document_record` in `backend/services/pdf_ingest.py`).

### Frontend E2E (Playwright)

```bash
pip install -r requirements-dev.txt
playwright install chromium
pytest tests/e2e -v
```

E2E tests use the `playwright` Python package directly (no `pytest-playwright` plugin required).

## Storage

All files are stored locally:

- `storage/originals/` — uploaded PDFs (never modified)
- `storage/work/` — working copies (OCR text layer) and applied (redacted) copies
- `storage/pages/` — rendered page PNGs (original and redacted)
- `storage/exports/` — exported PDFs and batch ZIPs
- `data/aud_it.db` — SQLite metadata

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents` | Upload PDFs (multi-file) |
| GET | `/api/documents` | List documents with statuses and finding counts |
| GET/DELETE | `/api/documents/{id}` | Document metadata / remove |
| GET | `/api/documents/{id}/pages/{n}/image?version=` | Page PNG (`original` or `redacted`) |
| GET | `/api/documents/{id}/pages/{n}/words` | Word bounding boxes |
| POST | `/api/documents/{id}/ocr` | Run OCR into the working copy |
| GET | `/api/findings` | List findings (masked) with filters |
| GET | `/api/findings/{id}/value` | Reveal a finding's value |
| POST | `/api/documents/{id}/findings` | Manual redaction box (page / all pages) |
| PATCH/DELETE | `/api/findings/{id}` | Update status or bbox / delete manual box |
| POST | `/api/findings/bulk` | Bulk approve/ignore/reset by filter |
| POST | `/api/findings/search` | Turn text-search matches into pending findings |
| POST | `/api/batch/detect` | Detect PII across documents (background) |
| POST | `/api/batch/apply` | Apply approved redactions + auto-verify (background) |
| POST | `/api/batch/verify` | Re-run verification (background) |
| POST | `/api/batch/export` | Export ZIP + reports |
| GET | `/api/documents/{id}/verification` | Verification report |
| GET/POST | `/api/rules` | List / create rules |
| PATCH/DELETE | `/api/rules/{id}` | Update / delete rule |
| POST | `/api/rules/suggest` | Suggest regex from examples |
| POST | `/api/rules/test` | Test a pattern against documents |
| GET | `/api/presidio/recognizers` | Selectable entity types |
| GET/POST | `/api/projects` | List / create projects |
| GET/PATCH/DELETE | `/api/projects/{id}` | Project detail / rename / delete |
| POST | `/api/projects/{id}/documents` | Upload PDFs to a project |
| GET | `/api/projects/{id}/pages` | Organize step page slots |
| PATCH | `/api/projects/{id}/pages/reorder` | Reorder page slots |
| POST | `/api/projects/{id}/pages/delete` | Delete page slots (batch) |
| POST | `/api/projects/{id}/merge-documents` | Merge documents by list order |
| POST | `/api/projects/{id}/organize/undo` | Undo organize action |
| POST | `/api/projects/{id}/organize/redo` | Redo organize action |
| POST | `/api/projects/{id}/advance` | Materialize pages → redact step |

## Presidio Exploration

Learn Presidio by defining custom recognizers and testing them on synthetic PDFs:

- Guide: [docs/PRESIDIO_EXPLORATION.md](docs/PRESIDIO_EXPLORATION.md)
- Recognizer files: `backend/presidio/recognizers/`
- Test corpus: `tests/redaction_test_pdfs/` (see `README_manifest.json`)
