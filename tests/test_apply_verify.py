import pymupdf as fitz
import pytest

from backend.database import Finding
from backend.schemas import FindingBulkFilter
from backend.services.apply import apply_redactions
from backend.services.findings import bulk_update, create_search_findings
from backend.services.pdf_ingest import current_pdf_path
from backend.services.text_extract import search_document
from backend.services.verify import VerifyError, verify_document
from tests.conftest import ingest_test_pdf


def _stage_search_findings(db, doc, term):
    pdf = fitz.open(str(current_pdf_path(doc)))
    matches = search_document(pdf, term)
    pdf.close()
    return create_search_findings(db, doc, term, matches)


def test_verify_requires_apply(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    with pytest.raises(VerifyError):
        verify_document(db, doc)


def test_apply_and_verify_multipage(db, manifest):
    doc = ingest_test_pdf(db, "03_multipage_repeated_pii.pdf")
    created = _stage_search_findings(db, doc, manifest["name"])
    assert len(created) >= 2  # repeated across pages

    bulk_update(db, "approve", FindingBulkFilter(document_ids=[doc.id]))
    applied = apply_redactions(db, doc)
    assert applied == len(created)

    # Applied copy no longer contains the name anywhere
    pdf = fitz.open(doc.applied_path)
    for page in pdf:
        assert not page.search_for(manifest["name"])
    pdf.close()

    report = verify_document(db, doc)
    by_name = {c.name: c for c in report.checks}
    assert by_name["search_test"].passed
    assert by_name["text_removed"].passed
    assert by_name["metadata_stripped"].passed
    assert by_name["annotations_flattened"].passed
    assert by_name["no_unresolved"].passed


def test_unsafe_overlay_pdf_truly_redacted(db, manifest):
    """PDF 06 has text 'hidden' under cosmetic black boxes. True redaction must
    remove the text, and our verification must prove it."""
    doc = ingest_test_pdf(db, "06_intentionally_unsafe_black_box_overlay.pdf")

    # The cosmetic overlay does NOT protect the text: it is still extractable
    pdf = fitz.open(str(current_pdf_path(doc)))
    extractable = any(page.search_for(manifest["ssn"]) for page in pdf)
    pdf.close()
    assert extractable, "expected the unsafe overlay PDF to leak its text"

    created = _stage_search_findings(db, doc, manifest["ssn"])
    assert created
    bulk_update(db, "approve", FindingBulkFilter(document_ids=[doc.id]))
    apply_redactions(db, doc)

    pdf = fitz.open(doc.applied_path)
    leaked = any(page.search_for(manifest["ssn"]) for page in pdf)
    pdf.close()
    assert not leaked

    report = verify_document(db, doc)
    assert {c.name: c.passed for c in report.checks}["search_test"]
    assert {c.name: c.passed for c in report.checks}["text_removed"]


def test_unresolved_pending_blocks_verification(db, manifest):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    _stage_search_findings(db, doc, manifest["name"])
    _stage_search_findings(db, doc, manifest["case"])

    # Approve only the name; the case id stays pending
    bulk_update(
        db,
        "approve",
        FindingBulkFilter(document_ids=[doc.id], value_key=manifest["name"].lower()),
    )
    apply_redactions(db, doc)
    report = verify_document(db, doc)

    assert not report.passed
    assert report.unresolved_pending > 0
    by_name = {c.name: c for c in report.checks}
    assert not by_name["no_unresolved"].passed


def test_reapply_after_more_approvals(db, manifest):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    _stage_search_findings(db, doc, manifest["name"])
    bulk_update(db, "approve", FindingBulkFilter(document_ids=[doc.id]))
    apply_redactions(db, doc)

    _stage_search_findings(db, doc, manifest["account"])
    bulk_update(db, "approve", FindingBulkFilter(document_ids=[doc.id]))
    apply_redactions(db, doc)

    pdf = fitz.open(doc.applied_path)
    assert not pdf[0].search_for(manifest["name"])
    assert not pdf[0].search_for(manifest["account"])
    pdf.close()

    statuses = {
        f.status for f in db.query(Finding).filter(Finding.document_id == doc.id).all()
    }
    assert statuses == {"applied"}
