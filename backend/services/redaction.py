import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Document, Export, Redaction
from backend.schemas import (
    BulkRedactResponse,
    ExportResponse,
    RedactionCreate,
    RedactionResponse,
    VerificationResponse,
)
from backend.services.metadata import strip_all
from backend.services.text_extract import search_document
from backend.services.verify import verify_export


def _to_response(redaction: Redaction) -> RedactionResponse:
    return RedactionResponse(
        id=redaction.id,
        document_id=redaction.document_id,
        page_num=redaction.page_num,
        x0=redaction.x0,
        y0=redaction.y0,
        x1=redaction.x1,
        y1=redaction.y1,
        source=redaction.source,
        search_term=redaction.search_term,
    )


def list_redactions(db: Session, document_id: str, page_num: int | None = None) -> list[RedactionResponse]:
    query = db.query(Redaction).filter(Redaction.document_id == document_id)
    if page_num is not None:
        query = query.filter(Redaction.page_num == page_num)
    return [_to_response(r) for r in query.order_by(Redaction.page_num, Redaction.id).all()]


def create_redaction(db: Session, document_id: str, payload: RedactionCreate) -> RedactionResponse:
    redaction = Redaction(
        document_id=document_id,
        page_num=payload.page_num,
        x0=payload.x0,
        y0=payload.y0,
        x1=payload.x1,
        y1=payload.y1,
        source=payload.source,
        search_term=payload.search_term,
    )
    db.add(redaction)
    db.commit()
    db.refresh(redaction)
    return _to_response(redaction)


def update_redaction(db: Session, redaction_id: int, x0: float, y0: float, x1: float, y1: float) -> RedactionResponse | None:
    redaction = db.get(Redaction, redaction_id)
    if not redaction:
        return None
    redaction.x0, redaction.y0, redaction.x1, redaction.y1 = x0, y0, x1, y1
    db.commit()
    db.refresh(redaction)
    return _to_response(redaction)


def delete_redaction(db: Session, redaction_id: int) -> bool:
    redaction = db.get(Redaction, redaction_id)
    if not redaction:
        return False
    db.delete(redaction)
    db.commit()
    return True


def bulk_redact_from_search(db: Session, document: Document, query: str) -> BulkRedactResponse:
    pdf = fitz.open(document.storage_path)
    matches = search_document(pdf, query)
    pdf.close()

    created: list[RedactionResponse] = []
    for match in matches:
        payload = RedactionCreate(
            page_num=match.page_num,
            x0=match.x0,
            y0=match.y0,
            x1=match.x1,
            y1=match.y1,
            source="search",
            search_term=query,
        )
        created.append(create_redaction(db, document.id, payload))

    return BulkRedactResponse(created=len(created), redactions=created)


def export_redacted_pdf(db: Session, document: Document) -> ExportResponse:
    redactions = (
        db.query(Redaction)
        .filter(Redaction.document_id == document.id)
        .order_by(Redaction.page_num, Redaction.id)
        .all()
    )

    export_id = str(uuid.uuid4())[:8]
    export_dir = settings.storage_dir / "exports" / document.id
    export_dir.mkdir(parents=True, exist_ok=True)
    export_filename = f"redacted_{export_id}.pdf"
    export_path = export_dir / export_filename

    pdf = fitz.open(document.storage_path)
    by_page: dict[int, list[Redaction]] = defaultdict(list)
    for redaction in redactions:
        by_page[redaction.page_num].append(redaction)

    for page_num, boxes in by_page.items():
        page = pdf[page_num]
        for box in boxes:
            rect = fitz.Rect(box.x0, box.y0, box.x1, box.y1)
            page.add_redact_annot(rect, fill=(0, 0, 0))
        page.apply_redactions()

    strip_all(pdf)
    temp_path = export_path.with_suffix(".tmp.pdf")
    pdf.save(str(temp_path), garbage=4, deflate=True)
    pdf.close()
    temp_path.replace(export_path)

    export_record = Export(
        document_id=document.id,
        output_path=str(export_path),
    )
    db.add(export_record)
    db.commit()
    db.refresh(export_record)

    verification = verify_export(db, export_record, redactions)

    return ExportResponse(
        export_id=export_record.id,
        filename=export_filename,
        download_url=f"/api/documents/{document.id}/exports/{export_record.id}/download",
        verification=verification,
    )


def get_latest_export(db: Session, document_id: str) -> Export | None:
    return (
        db.query(Export)
        .filter(Export.document_id == document_id)
        .order_by(Export.id.desc())
        .first()
    )


def verify_latest_export(db: Session, document: Document) -> VerificationResponse | None:
    export_record = get_latest_export(db, document.id)
    if not export_record:
        return None
    redactions = db.query(Redaction).filter(Redaction.document_id == document.id).all()
    return verify_export(db, export_record, redactions)
