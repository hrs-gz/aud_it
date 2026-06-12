from pathlib import Path

from backend.database import Finding
from backend.schemas import FindingBulkFilter, ManualFindingCreate
from backend.services.findings import (
    Occurrence,
    bulk_update,
    create_manual_findings,
    mask_value,
    persist_occurrences,
    value_key_for,
)
from tests.conftest import ingest_test_pdf


def test_mask_value_formats():
    assert mask_value("A123456789") == "A\u2022\u2022\u2022\u2022\u2022\u2022789"
    assert mask_value("Jordan Avery") == "J\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022ery"
    assert mask_value("ab") == "\u2022\u2022"
    assert mask_value("abcd") == "a\u2022\u2022\u2022"
    assert mask_value(None) is None
    # Never echo the raw value
    assert "123456" not in mask_value("A123456789")


def test_value_key_normalizes():
    assert value_key_for("  Jordan   AVERY ") == "jordan avery"
    assert value_key_for(None) is None


def _occurrence(page=0, entity="US_SSN", text="123-45-6789", score=0.85):
    return Occurrence(
        page_num=page,
        entity_type=entity,
        text=text,
        score=score,
        rects=[(10.0, 10.0, 80.0, 20.0)],
    )


def test_persist_occurrences_statuses(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")

    created = persist_occurrences(
        db,
        doc,
        [
            _occurrence(score=0.9),
            _occurrence(entity="PERSON", text="Jordan Avery", score=0.45),
        ],
    )
    assert created == 2

    findings = db.query(Finding).filter(Finding.document_id == doc.id).all()
    by_entity = {f.entity_type: f for f in findings}
    assert by_entity["US_SSN"].status == "pending"
    # Low confidence routes to needs_review
    assert by_entity["PERSON"].status == "needs_review"
    assert by_entity["PERSON"].value_key == "jordan avery"


def test_redetect_preserves_decisions(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    persist_occurrences(db, doc, [_occurrence(score=0.9)])

    finding = db.query(Finding).filter(Finding.document_id == doc.id).one()
    finding.status = "approved"
    db.commit()

    # Re-run detection with the same occurrence: decision must survive
    persist_occurrences(db, doc, [_occurrence(score=0.9)])
    finding = db.query(Finding).filter(Finding.document_id == doc.id).one()
    assert finding.status == "approved"


def test_bulk_update_never_touches_applied(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    persist_occurrences(db, doc, [_occurrence(score=0.9)])
    finding = db.query(Finding).filter(Finding.document_id == doc.id).one()
    finding.status = "applied"
    db.commit()

    updated = bulk_update(db, "ignore", FindingBulkFilter(document_ids=[doc.id]))
    assert updated == 0
    db.refresh(finding)
    assert finding.status == "applied"


def test_manual_findings_all_pages_start_approved(db):
    doc = ingest_test_pdf(db, "03_multipage_repeated_pii.pdf")
    created = create_manual_findings(
        db,
        doc,
        ManualFindingCreate(page_num=0, x0=10, y0=10, x1=100, y1=30, all_pages=True),
    )
    assert len(created) == doc.page_count
    assert all(f.status == "approved" for f in created)
    assert all(f.source == "manual" for f in created)


def test_original_pdf_never_modified(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    original_bytes = Path(doc.storage_path).read_bytes()

    persist_occurrences(db, doc, [_occurrence(score=0.9)])
    bulk_update(db, "approve", FindingBulkFilter(document_ids=[doc.id]))

    from backend.services.apply import apply_redactions

    apply_redactions(db, doc)
    assert Path(doc.applied_path).exists()
    assert Path(doc.storage_path).read_bytes() == original_bytes
