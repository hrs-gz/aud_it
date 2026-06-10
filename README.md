# aud_it

Local-first PDF redaction web app. Upload a PDF, draw or search for redaction boxes, and export a destructively redacted copy. No cloud services or paid APIs.

## Features

- Upload PDFs and render pages as images
- Word-level text extraction with PyMuPDF
- Search text and redact all matches
- Manually draw, move, resize, and delete redaction boxes
- Export redacted PDFs with metadata stripped
- Post-export verification that redacted terms are no longer extractable
- OCR fallback for scanned documents (OCRmyPDF / Tesseract)
- Optional PII detection with Microsoft Presidio (local models)

## Requirements

- Python 3.11+
- [Tesseract](https://github.com/tesseract-ocr/tesseract) (for OCR): `brew install tesseract`
- [OCRmyPDF](https://ocrmypdf.readthedocs.io/) (optional, for scanned PDFs): `brew install ocrmypdf`

For Presidio PII detection (optional):

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
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000

## Storage

All files are stored locally:

- `storage/originals/` — uploaded PDFs (never modified)
- `storage/pages/` — rendered page PNGs
- `storage/exports/` — redacted output PDFs
- `storage/work/` — temporary OCR working copies
- `data/aud_it.db` — SQLite metadata

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents` | Upload PDF |
| GET | `/api/documents/{id}` | Document metadata |
| GET | `/api/documents/{id}/pages/{n}/image` | Page PNG |
| GET | `/api/documents/{id}/pages/{n}/words` | Word bounding boxes |
| GET | `/api/documents/{id}/search?q=term` | Search text |
| GET/POST/PUT/DELETE | `/api/documents/{id}/redactions` | Redaction CRUD |
| POST | `/api/documents/{id}/redactions/bulk` | Bulk add from search |
| POST | `/api/documents/{id}/export` | Export redacted PDF |
| GET | `/api/documents/{id}/verify` | Verify export |
| POST | `/api/documents/{id}/ocr` | Run OCR on scanned PDF |
| POST | `/api/documents/{id}/detect-pii` | Detect PII with Presidio |
