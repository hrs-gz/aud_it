import json
import zipfile
from pathlib import Path

import pymupdf as fitz

from backend.schemas import FindingBulkFilter
from backend.services.apply import apply_redactions
from backend.services.export import batch_zip_path, export_batch
from backend.services.findings import bulk_update, create_search_findings
from backend.services.pdf_ingest import current_pdf_path
from backend.services.text_extract import search_document
from backend.services.verify import verify_document
from tests.conftest import ingest_test_pdf


def _prepare_applied_doc(db, name, term):
    doc = ingest_test_pdf(db, name)
    pdf = fitz.open(str(current_pdf_path(doc)))
    matches = search_document(pdf, term)
    pdf.close()
    create_search_findings(db, doc, term, matches)
    bulk_update(db, "approve", FindingBulkFilter(document_ids=[doc.id]))
    apply_redactions(db, doc)
    verify_document(db, doc)
    return doc


def test_export_blocked_without_apply(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    result = export_batch(db, [doc], allow_unverified=False)
    assert result.items[0].skipped_reason
    assert result.zip_url is None


def test_batch_export_zip_contents(db, manifest):
    doc1 = _prepare_applied_doc(db, "01_text_pii_letter.pdf", manifest["name"])
    doc2 = _prepare_applied_doc(db, "03_multipage_repeated_pii.pdf", manifest["name"])

    result = export_batch(db, [doc1, doc2], allow_unverified=True)
    assert result.zip_url

    zip_path = batch_zip_path(result.batch_id)
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "audit_report.json" in names
        assert "redaction_summary.csv" in names
        assert "verification_report.json" in names
        pdf_names = [n for n in names if n.endswith(".pdf")]
        assert len(pdf_names) == 2

        audit = json.loads(zf.read("audit_report.json"))
        assert audit["documents_processed"] == 2
        assert audit["total_redactions"] >= 2

        # Privacy: reports must not leak raw values
        report_text = (
            zf.read("audit_report.json")
            + zf.read("redaction_summary.csv")
            + zf.read("verification_report.json")
        ).decode("utf-8", errors="replace")
        for value in (manifest["name"], manifest["ssn"], manifest["account"]):
            assert value not in report_text

        # Exported PDFs are the redacted copies
        for pdf_name in pdf_names:
            data = zf.read(pdf_name)
            pdf = fitz.open(stream=data, filetype="pdf")
            for page in pdf:
                assert not page.search_for(manifest["name"])
            assert not any(v for k, v in (pdf.metadata or {}).items() if k not in ("format", "encryption"))
            pdf.close()


def test_export_skips_unverified_unless_allowed(db, manifest):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    pdf = fitz.open(str(current_pdf_path(doc)))
    matches = search_document(pdf, manifest["name"])
    pdf.close()
    create_search_findings(db, doc, manifest["name"], matches)
    # Stage a second value but never decide on it -> verification fails
    create_search_findings(db, doc, manifest["case"], [])
    bulk_update(
        db,
        "approve",
        FindingBulkFilter(document_ids=[doc.id], value_key=manifest["name"].lower()),
    )
    pdf = fitz.open(str(current_pdf_path(doc)))
    case_matches = search_document(pdf, manifest["case"])
    pdf.close()
    create_search_findings(db, doc, manifest["case"], case_matches)

    apply_redactions(db, doc)
    verify_document(db, doc)

    strict = export_batch(db, [doc], allow_unverified=False)
    assert strict.items[0].skipped_reason
    assert strict.warnings

    forced = export_batch(db, [doc], allow_unverified=True)
    assert forced.items[0].download_url
    assert Path(batch_zip_path(forced.batch_id)).exists()
