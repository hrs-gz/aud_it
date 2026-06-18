"""Background batch pipeline: detect / apply / verify across documents.

Each runner opens its own DB session (FastAPI BackgroundTasks run after the
request session closes) and walks documents sequentially, updating
Document.status so the UI can poll progress. No document text is ever logged."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.database import (
    DOC_STATUS_APPLYING,
    DOC_STATUS_DETECTING,
    DOC_STATUS_ERROR,
    DOC_STATUS_EXPORTING,
    DOC_STATUS_OCR,
    DOC_STATUS_READY,
    DOC_STATUS_VERIFYING,
    Document,
    SessionLocal,
)
from backend.services.apply import apply_redactions
from backend.services.findings import persist_occurrences
from backend.services.ocr import OCRError, run_ocr
from backend.services.rules import build_ad_hoc_recognizers, list_rules
from backend.services.verify import VerifyError, verify_document

_BUSY_STATUSES = {
    DOC_STATUS_OCR,
    DOC_STATUS_DETECTING,
    DOC_STATUS_APPLYING,
    DOC_STATUS_VERIFYING,
    DOC_STATUS_EXPORTING,
}


def recover_interrupted_jobs() -> int:
    """Reset documents left in a busy status after a server restart."""
    db = SessionLocal()
    try:
        stuck = db.query(Document).filter(Document.status.in_(_BUSY_STATUSES)).all()
        for document in stuck:
            document.status = DOC_STATUS_ERROR
            document.status_detail = "Interrupted — run detection again"
        if stuck:
            db.commit()
        return len(stuck)
    finally:
        db.close()


def _set_status(db: Session, document: Document, status: str, detail: str | None = None) -> None:
    document.status = status
    document.status_detail = detail
    db.commit()


def detect_one(
    db: Session,
    document: Document,
    entities: list[str] | None,
    score_threshold: float,
    auto_ocr: bool,
) -> int:
    from backend.services.presidio import analyze_document

    if auto_ocr and document.is_scanned:
        _set_status(db, document, DOC_STATUS_OCR, "Running OCR")
        try:
            run_ocr(db, document)
        except OCRError as exc:
            # Detection continues on whatever text layer exists.
            document.status_detail = f"OCR failed: {exc}"
            db.commit()

    _set_status(db, document, DOC_STATUS_DETECTING, "Detecting PII")
    rules = list_rules(db, enabled_only=True)
    ad_hoc, rule_entity_types = build_ad_hoc_recognizers(rules)
    occurrences = analyze_document(
        document,
        entities=entities,
        score_threshold=score_threshold,
        ad_hoc_recognizers=ad_hoc,
        rule_entity_types=rule_entity_types,
    )
    created = persist_occurrences(
        db, document, occurrences, rules_by_id={r.id: r for r in rules}
    )
    document.detected_at = datetime.now(timezone.utc)
    db.commit()
    return created


def run_batch_detect(
    document_ids: list[str],
    entities: list[str] | None,
    score_threshold: float,
    auto_ocr: bool,
) -> None:
    db = SessionLocal()
    try:
        for doc_id in document_ids:
            document = db.get(Document, doc_id)
            if not document:
                continue
            try:
                detect_one(db, document, entities, score_threshold, auto_ocr)
                _set_status(db, document, DOC_STATUS_READY, None)
            except Exception as exc:
                db.rollback()
                _set_status(db, document, DOC_STATUS_ERROR, f"Detection failed: {exc}")
    finally:
        db.close()


def run_batch_apply(document_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        for doc_id in document_ids:
            document = db.get(Document, doc_id)
            if not document:
                continue
            try:
                _set_status(db, document, DOC_STATUS_APPLYING, "Applying redactions")
                apply_redactions(db, document)
                _set_status(db, document, DOC_STATUS_VERIFYING, "Verifying")
                verify_document(db, document)
                _set_status(db, document, DOC_STATUS_READY, None)
            except Exception as exc:
                db.rollback()
                _set_status(db, document, DOC_STATUS_ERROR, f"Apply failed: {exc}")
    finally:
        db.close()


def run_batch_verify(document_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        for doc_id in document_ids:
            document = db.get(Document, doc_id)
            if not document:
                continue
            try:
                _set_status(db, document, DOC_STATUS_VERIFYING, "Verifying")
                verify_document(db, document)
                _set_status(db, document, DOC_STATUS_READY, None)
            except VerifyError as exc:
                _set_status(db, document, DOC_STATUS_READY, str(exc))
            except Exception as exc:
                db.rollback()
                _set_status(db, document, DOC_STATUS_ERROR, f"Verify failed: {exc}")
    finally:
        db.close()
