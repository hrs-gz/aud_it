from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import Document, get_db
from backend.schemas import (
    BulkRedactRequest,
    BulkRedactResponse,
    ExportResponse,
    RedactionCreate,
    RedactionResponse,
    RedactionUpdate,
    VerificationResponse,
)
from backend.services.redaction import (
    bulk_redact_from_search,
    create_redaction,
    delete_redaction,
    export_redacted_pdf,
    list_redactions,
    update_redaction,
    verify_latest_export,
)

router = APIRouter(prefix="/api", tags=["redactions"])


def _get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents/{document_id}/redactions", response_model=list[RedactionResponse])
def get_redactions(document_id: str, page: int | None = None, db: Session = Depends(get_db)):
    _get_document(db, document_id)
    return list_redactions(db, document_id, page)


@router.post("/documents/{document_id}/redactions", response_model=RedactionResponse)
def add_redaction(
    document_id: str,
    payload: RedactionCreate,
    db: Session = Depends(get_db),
):
    _get_document(db, document_id)
    return create_redaction(db, document_id, payload)


@router.put("/redactions/{redaction_id}", response_model=RedactionResponse)
def edit_redaction(redaction_id: int, payload: RedactionUpdate, db: Session = Depends(get_db)):
    result = update_redaction(db, redaction_id, payload.x0, payload.y0, payload.x1, payload.y1)
    if not result:
        raise HTTPException(status_code=404, detail="Redaction not found")
    return result


@router.delete("/redactions/{redaction_id}")
def remove_redaction(redaction_id: int, db: Session = Depends(get_db)):
    if not delete_redaction(db, redaction_id):
        raise HTTPException(status_code=404, detail="Redaction not found")
    return {"deleted": True}


@router.post("/documents/{document_id}/redactions/bulk", response_model=BulkRedactResponse)
def bulk_redact(document_id: str, payload: BulkRedactRequest, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    return bulk_redact_from_search(db, document, payload.query)


@router.post("/documents/{document_id}/export", response_model=ExportResponse)
def export_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    return export_redacted_pdf(db, document)


@router.get("/documents/{document_id}/verify", response_model=VerificationResponse)
def verify_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    result = verify_latest_export(db, document)
    if not result:
        raise HTTPException(status_code=404, detail="No export found to verify")
    return result
