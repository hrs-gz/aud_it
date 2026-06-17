# Presidio Exploration Guide

This guide walks through adding and testing custom Presidio recognizers on the aud_it backbone.

## Prerequisites

Install Presidio and the spaCy English model (see [README](../README.md)):

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg
```

Start the app:

```bash
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000

## Learning flow

1. **Edit a recognizer** in `backend/presidio/recognizers/`
2. **Register it** in `backend/presidio/recognizers/__init__.py`
3. **Add catalog metadata** in `backend/presidio/catalog.py` (for the MVP checklist)
4. **Restart the server** (analyzer is cached at startup)
5. **Upload a test PDF** and select your entity types in the PII Detection panel
6. **Detect PII** — purple overlays show hits on the canvas; the sidebar lists each match
7. Compare results against expected values in `tests/redaction_test_pdfs/README_manifest.json`

Optional: check hits you want to redact → **Apply selected PII** → **Export redacted PDF**.

## Add a custom recognizer

### 1. Copy the template

Start from `backend/presidio/recognizers/_template.py` or an existing file like `mrn.py`:

```python
from presidio_analyzer import Pattern, PatternRecognizer

MY_PATTERN = Pattern(
    name="my_pattern",
    regex=r"YOUR-REGEX-HERE",
    score=0.85,
)

MY_RECOGNIZER = PatternRecognizer(
    supported_entity="MY_ENTITY_TYPE",
    patterns=[MY_PATTERN],
    context=["optional", "context", "words"],
)
```

Context words boost confidence when they appear near the match.

### 2. Register the recognizer

Add your recognizer to `get_custom_recognizers()` in `backend/presidio/recognizers/__init__.py`:

```python
from backend.presidio.recognizers.my_module import MY_RECOGNIZER

def get_custom_recognizers() -> list[EntityRecognizer]:
    return [
        MRN_RECOGNIZER,
        ACCOUNT_RECOGNIZER,
        CASE_ID_RECOGNIZER,
        MY_RECOGNIZER,
    ]
```

### 3. Add catalog entry

Add a row to `CUSTOM_CATALOG` in `backend/presidio/catalog.py` so the MVP shows your entity:

```python
RecognizerCatalogEntry(
    entity_type="MY_ENTITY_TYPE",
    label="My Field",
    description="What this detects",
    group="custom",
    custom=True,
    default_enabled=True,
)
```

### 4. Restart and test

Restart uvicorn, then upload `tests/redaction_test_pdfs/01_text_pii_letter.pdf`.

Select only your entity type → **Detect PII**.

## Starter recognizers

These ship with the project and target fake values in the test corpus:

| Entity | Pattern | Example value |
|--------|---------|---------------|
| `MEDICAL_RECORD_NUMBER` | `MRN-\d{8}` | MRN-00048192 (manifest value; test via synthetic text or add to a PDF) |
| `ACCOUNT_NUMBER` | `ACCT-\d{4}-\d{4}-\d{4}` | ACCT-9842-7710-5531 |
| `CASE_ID` | `CASE-\d{4}-\d{5}` | CASE-2026-01984 |
| `US_ADDRESS` | `EntityRecognizer` + `usaddress.tag()` | 742 Maple Ridge Lane, Austin, TX 78701 |

`US_ADDRESS` is an NLP-based recognizer (not regex): see `backend/presidio/recognizers/us_address.py`.

Built-in Presidio entities (email, phone, SSN, etc.) are also selectable in the **Built-in** group.

## Test corpus

Synthetic PDFs live in `tests/redaction_test_pdfs/`:

| File | Focus |
|------|-------|
| `01_text_pii_letter.pdf` | Baseline text PII — start here |
| `02_table_mixed_identifiers.pdf` | Table/cell bounding boxes |
| `03_multipage_repeated_pii.pdf` | Same PII on multiple pages |
| `04_rotated_and_small_text.pdf` | Coordinate mapping edge cases |
| `05_scanned_image_pdf_needs_ocr.pdf` | Run OCR first |
| `08_form_like_layout.pdf` | Form-style layout |

Expected fake values: `tests/redaction_test_pdfs/README_manifest.json`

## CLI smoke test

Run pytest (skips if Presidio is not installed):

```bash
pytest tests/test_presidio_custom_recognizers.py -v
```

## Architecture

```
PDF page words → join text → Presidio analyze(entities=[...])
  → character spans → map to word bounding boxes → PIISuggestion list
  → MVP sidebar + purple canvas overlays
```

Recognizer definitions: `backend/presidio/recognizers/`
Detection pipeline: `backend/presidio/analyzer.py`
API: `GET /api/presidio/recognizers`, `POST /api/documents/{id}/detect-pii`
