import json
import sys
from pathlib import Path

import pymupdf as fitz
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.text_extract import extract_words

pytest.importorskip("presidio_analyzer")
pytest.importorskip("spacy")

TEST_PDF = ROOT / "tests" / "redaction_test_pdfs" / "01_text_pii_letter.pdf"
MANIFEST = ROOT / "tests" / "redaction_test_pdfs" / "README_manifest.json"

CUSTOM_ENTITIES = [
    "MEDICAL_RECORD_NUMBER",
    "ACCOUNT_NUMBER",
    "CASE_ID",
]


def _extract_page_text(pdf_path: Path) -> str:
    pdf = fitz.open(pdf_path)
    parts: list[str] = []
    for page in pdf:
        words = extract_words(page)
        if words:
            parts.append(" ".join(w.text for w in words))
    pdf.close()
    return " ".join(parts)


@pytest.fixture(scope="module")
def manifest_values() -> dict:
    data = json.loads(MANIFEST.read_text())
    return data["fake_values"]


@pytest.fixture(scope="module")
def letter_text() -> str:
    if not TEST_PDF.exists():
        pytest.skip(f"Test PDF not found: {TEST_PDF}")
    return _extract_page_text(TEST_PDF)


@pytest.fixture(scope="module")
def analyzer():
    from backend.presidio.registry import build_analyzer

    try:
        return build_analyzer()
    except Exception as exc:
        pytest.skip(f"Presidio analyzer unavailable: {exc}")


def test_custom_recognizers_detect_ids_in_letter_pdf(analyzer, letter_text, manifest_values):
    results = analyzer.analyze(
        text=letter_text,
        language="en",
        entities=CUSTOM_ENTITIES,
        score_threshold=0.5,
    )

    detected_texts = {letter_text[r.start : r.end] for r in results}
    detected_by_entity = {r.entity_type: letter_text[r.start : r.end] for r in results}

    assert manifest_values["account"] in detected_texts
    assert manifest_values["case"] in detected_texts
    assert detected_by_entity.get("ACCOUNT_NUMBER") == manifest_values["account"]
    assert detected_by_entity.get("CASE_ID") == manifest_values["case"]


def test_mrn_recognizer_matches_manifest_pattern(analyzer, manifest_values):
    sample = f"Patient record {manifest_values['mrn']} for intake."
    results = analyzer.analyze(
        text=sample,
        language="en",
        entities=["MEDICAL_RECORD_NUMBER"],
        score_threshold=0.5,
    )

    detected = {sample[r.start : r.end] for r in results}
    assert manifest_values["mrn"] in detected


def test_list_recognizers_includes_custom_entities():
    from backend.services.presidio import list_recognizers

    try:
        catalog = list_recognizers()
    except Exception as exc:
        pytest.skip(f"Presidio unavailable: {exc}")

    if len(catalog) == 1 and catalog[0].entity_type == "_error":
        pytest.skip(catalog[0].description)

    entity_types = {entry.entity_type for entry in catalog}
    for entity in CUSTOM_ENTITIES:
        assert entity in entity_types
