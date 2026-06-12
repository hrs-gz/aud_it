from pathlib import Path

import pymupdf as fitz
import pytest

import backend.services.ocr as ocr_module
from backend.services.pdf_ingest import current_pdf_path
from tests.conftest import ingest_test_pdf, tesseract_available

pytestmark = pytest.mark.skipif(not tesseract_available(), reason="Tesseract unavailable")


def test_tesseract_fallback_produces_text_layer(db, monkeypatch, manifest):
    doc = ingest_test_pdf(db, "05_scanned_image_pdf_needs_ocr.pdf")
    assert doc.is_scanned
    assert sum(p.word_count for p in doc.pages) == 0

    original_bytes = Path(doc.storage_path).read_bytes()

    # Force the PyMuPDF/Tesseract path even if OCRmyPDF is installed
    monkeypatch.setattr(ocr_module, "_ocrmypdf_available", lambda: False)
    result = ocr_module.run_ocr(db, doc)

    assert result.success
    assert result.total_words > 0
    assert not result.errors

    # OCR went to the working copy; the original is byte-identical
    assert doc.working_path
    assert Path(doc.working_path).read_bytes() != original_bytes
    assert Path(doc.storage_path).read_bytes() == original_bytes

    # The working copy is genuinely searchable
    pdf = fitz.open(str(current_pdf_path(doc)))
    page_text = pdf[0].get_text()
    pdf.close()
    assert manifest["name"] in page_text
