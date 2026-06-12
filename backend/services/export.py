import csv
import io
import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import FINDING_APPLIED, Document, Export, Finding
from backend.schemas import (
    ExportBatchResponse,
    ExportItemResult,
    VerificationReport,
)
from backend.services.findings import mask_value
from backend.services.verify import stored_report, verify_document


def _safe_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_") or "document"
    return f"redacted_{stem}.pdf"


def export_document(
    db: Session, document: Document, allow_unverified: bool = False
) -> tuple[ExportItemResult, VerificationReport | None]:
    if not document.applied_path or not Path(document.applied_path).exists():
        return (
            ExportItemResult(
                document_id=document.id,
                skipped_reason="No applied redactions. Apply before exporting.",
            ),
            None,
        )

    report = stored_report(document)
    if report is None:
        report = verify_document(db, document)

    if not report.passed and not allow_unverified:
        return (
            ExportItemResult(
                document_id=document.id,
                verification_passed=False,
                skipped_reason="Verification found unresolved issues. Review remaining or export anyway.",
            ),
            report,
        )

    export_dir = settings.storage_dir / "exports" / document.id
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_name(document.original_filename)
    export_path = export_dir / filename
    shutil.copy2(document.applied_path, export_path)

    export_record = Export(
        document_id=document.id,
        output_path=str(export_path),
        verified_at=document.verified_at,
        verification_json=document.verification_json,
    )
    db.add(export_record)
    document.exported_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(export_record)

    return (
        ExportItemResult(
            document_id=document.id,
            filename=filename,
            download_url=f"/api/documents/{document.id}/exports/{export_record.id}/download",
            verification_passed=report.passed,
        ),
        report,
    )


def _redaction_summary_csv(db: Session, documents: list[Document]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["document", "page", "entity_type", "masked_value", "source", "rule", "confidence"]
    )
    for document in documents:
        findings = (
            db.query(Finding)
            .filter(Finding.document_id == document.id, Finding.status == FINDING_APPLIED)
            .order_by(Finding.page_num, Finding.id)
            .all()
        )
        for f in findings:
            writer.writerow(
                [
                    document.original_filename,
                    f.page_num + 1,
                    f.entity_type,
                    mask_value(f.text) or "",
                    f.source,
                    f.rule.name if f.rule else "",
                    f"{f.confidence:.2f}",
                ]
            )
    return buffer.getvalue()


def _audit_report(
    db: Session,
    documents: list[Document],
    items: list[ExportItemResult],
) -> dict:
    """Audit report with counts only — no sensitive text snippets."""
    rules_used: set[str] = set()
    doc_entries = []
    total_redactions = 0

    items_by_doc = {item.document_id: item for item in items}

    for document in documents:
        findings = db.query(Finding).filter(Finding.document_id == document.id).all()
        applied = [f for f in findings if f.status == FINDING_APPLIED]
        total_redactions += len(applied)
        for f in applied:
            if f.rule:
                rules_used.add(f.rule.name)

        detected_by_type: dict[str, int] = {}
        redacted_by_type: dict[str, int] = {}
        for f in findings:
            detected_by_type[f.entity_type] = detected_by_type.get(f.entity_type, 0) + 1
        for f in applied:
            redacted_by_type[f.entity_type] = redacted_by_type.get(f.entity_type, 0) + 1

        report = stored_report(document)
        item = items_by_doc.get(document.id)
        doc_entries.append(
            {
                "filename": document.original_filename,
                "pages": document.page_count,
                "detected_by_type": detected_by_type,
                "redacted_by_type": redacted_by_type,
                "redaction_count": len(applied),
                "pages_affected": sorted({f.page_num + 1 for f in applied}),
                "verification_passed": report.passed if report else None,
                "exported": bool(item and item.download_url),
                "skipped_reason": item.skipped_reason if item else None,
            }
        )

    return {
        "project": "aud_it",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents_processed": len(documents),
        "total_redactions": total_redactions,
        "rules_used": sorted(rules_used),
        "documents": doc_entries,
    }


def export_batch(
    db: Session, documents: list[Document], allow_unverified: bool = False
) -> ExportBatchResponse:
    items: list[ExportItemResult] = []
    reports: dict[str, VerificationReport | None] = {}
    warnings: list[str] = []

    for document in documents:
        item, report = export_document(db, document, allow_unverified=allow_unverified)
        items.append(item)
        reports[document.id] = report
        if item.skipped_reason:
            warnings.append(f"{document.original_filename}: {item.skipped_reason}")
        elif report and not report.passed:
            warnings.append(
                f"{document.original_filename}: exported with unresolved verification issues"
            )

    batch_id = str(uuid.uuid4())[:8]
    batch_dir = settings.storage_dir / "exports" / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    zip_path = batch_dir / f"{batch_id}.zip"

    audit = _audit_report(db, documents, items)
    csv_text = _redaction_summary_csv(db, documents)
    verification_payload = {
        doc.id: (reports[doc.id].model_dump(mode="json") if reports[doc.id] else None)
        for doc in documents
    }
    verification_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": {
            doc.original_filename: verification_payload[doc.id] for doc in documents
        },
    }

    exported_any = False
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names: set[str] = set()
        for document, item in zip(documents, items):
            if not item.filename:
                continue
            export_record = (
                db.query(Export)
                .filter(Export.document_id == document.id)
                .order_by(Export.id.desc())
                .first()
            )
            if not export_record or not Path(export_record.output_path).exists():
                continue
            name = item.filename
            if name in used_names:
                name = f"{Path(name).stem}_{document.id[:8]}.pdf"
            used_names.add(name)
            zf.write(export_record.output_path, name)
            exported_any = True

        zf.writestr("audit_report.json", json.dumps(audit, indent=2))
        zf.writestr("redaction_summary.csv", csv_text)
        zf.writestr("verification_report.json", json.dumps(verification_report, indent=2))

    return ExportBatchResponse(
        batch_id=batch_id,
        zip_url=f"/api/exports/batch/{batch_id}/download" if exported_any else None,
        items=items,
        warnings=warnings,
    )


def batch_zip_path(batch_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f-]{1,36}", batch_id):
        raise ValueError("Invalid batch id")
    return settings.storage_dir / "exports" / "batch" / f"{batch_id}.zip"
