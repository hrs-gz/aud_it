from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import (
    DOC_STATUS_APPLYING,
    DOC_STATUS_DETECTING,
    DOC_STATUS_OCR,
    DOC_STATUS_VERIFYING,
    Document,
    get_db,
)
from backend.schemas import (
    BatchAcceptedResponse,
    BatchApplyRequest,
    BatchDetectRequest,
    BatchExportRequest,
    BatchVerifyRequest,
    ExportBatchResponse,
    VerificationReport,
)
from backend.services.batch import run_batch_apply, run_batch_detect, run_batch_verify
from backend.services.export import batch_zip_path, export_batch
from backend.services.verify import VerifyError, verify_document

router = APIRouter(prefix="/api", tags=["batch"])

_BUSY_STATUSES = {DOC_STATUS_OCR, DOC_STATUS_DETECTING, DOC_STATUS_APPLYING, DOC_STATUS_VERIFYING}


def _validate_documents(db: Session, document_ids: list[str]) -> list[Document]:
    if not document_ids:
        raise HTTPException(status_code=400, detail="No documents selected")
    documents = []
    for doc_id in document_ids:
        document = db.get(Document, doc_id)
        if not document:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
        documents.append(document)
    busy = [d.original_filename for d in documents if d.status in _BUSY_STATUSES]
    if busy:
        raise HTTPException(
            status_code=409,
            detail=f"Documents are busy: {', '.join(busy)}",
        )
    return documents


@router.post("/batch/detect", response_model=BatchAcceptedResponse)
def batch_detect(
    payload: BatchDetectRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    documents = _validate_documents(db, payload.document_ids)
    for document in documents:
        document.status = DOC_STATUS_DETECTING
        document.status_detail = "Queued for detection"
    db.commit()

    background.add_task(
        run_batch_detect,
        [d.id for d in documents],
        payload.entities,
        payload.score_threshold,
        payload.auto_ocr,
    )
    return BatchAcceptedResponse(
        accepted=True,
        document_ids=[d.id for d in documents],
        message=f"Detection started for {len(documents)} document(s)",
    )


@router.post("/batch/apply", response_model=BatchAcceptedResponse)
def batch_apply(
    payload: BatchApplyRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    documents = _validate_documents(db, payload.document_ids)
    for document in documents:
        document.status = DOC_STATUS_APPLYING
        document.status_detail = "Queued for apply"
    db.commit()

    background.add_task(run_batch_apply, [d.id for d in documents])
    return BatchAcceptedResponse(
        accepted=True,
        document_ids=[d.id for d in documents],
        message=f"Applying redactions to {len(documents)} document(s)",
    )


@router.post("/batch/verify", response_model=BatchAcceptedResponse)
def batch_verify(
    payload: BatchVerifyRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    documents = _validate_documents(db, payload.document_ids)
    for document in documents:
        document.status = DOC_STATUS_VERIFYING
        document.status_detail = "Queued for verification"
    db.commit()

    background.add_task(run_batch_verify, [d.id for d in documents])
    return BatchAcceptedResponse(
        accepted=True,
        document_ids=[d.id for d in documents],
        message=f"Verifying {len(documents)} document(s)",
    )


@router.get("/documents/{document_id}/verification", response_model=VerificationReport)
def get_verification(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    from backend.services.verify import stored_report

    report = stored_report(document)
    if report is None:
        try:
            report = verify_document(db, document)
        except VerifyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return report


@router.post("/batch/export", response_model=ExportBatchResponse)
def batch_export(payload: BatchExportRequest, db: Session = Depends(get_db)):
    documents = _validate_documents(db, payload.document_ids)
    return export_batch(db, documents, allow_unverified=payload.allow_unverified)


@router.get("/exports/batch/{batch_id}/download")
def download_batch(batch_id: str):
    try:
        path = batch_zip_path(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Batch export not found")
    return FileResponse(
        path, media_type="application/zip", filename=f"redacted_batch_{batch_id}.zip"
    )
