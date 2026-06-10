from pathlib import Path

import pymupdf as fitz
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import Document, Export, get_db
from backend.schemas import (
    DocumentResponse,
    OCRResponse,
    PageInfo,
    PIIBulkRequest,
    PIIDetectResponse,
    SearchResponse,
    WordsResponse,
)
from backend.services.ocr import OCRError, run_ocr
from backend.services.pdf_ingest import ingest_pdf
from backend.services.presidio import detect_pii
from backend.services.redaction import create_redaction
from backend.services.text_extract import extract_words, search_document
from backend.schemas import RedactionCreate

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        original_filename=document.original_filename,
        page_count=document.page_count,
        is_scanned=document.is_scanned,
        render_scale=document.render_scale,
        status=document.status,
        created_at=document.created_at,
        pages=[PageInfo(page_num=p.page_num, word_count=p.word_count) for p in document.pages],
    )


@router.post("", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    document = ingest_pdf(db, file.filename, content)
    return _document_response(document)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    return _document_response(_get_document(db, document_id))


@router.get("/{document_id}/pages/{page_num}/image")
def get_page_image(document_id: str, page_num: int, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    if page_num < 0 or page_num >= document.page_count:
        raise HTTPException(status_code=404, detail="Page not found")

    page = next((p for p in document.pages if p.page_num == page_num), None)
    if not page or not Path(page.image_path).exists():
        raise HTTPException(status_code=404, detail="Page image not found")

    return FileResponse(page.image_path, media_type="image/png")


@router.get("/{document_id}/pages/{page_num}/words", response_model=WordsResponse)
def get_page_words(document_id: str, page_num: int, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    if page_num < 0 or page_num >= document.page_count:
        raise HTTPException(status_code=404, detail="Page not found")

    pdf = fitz.open(document.storage_path)
    words = extract_words(pdf[page_num])
    pdf.close()

    return WordsResponse(page_num=page_num, words=words)


@router.get("/{document_id}/search", response_model=SearchResponse)
def search_document_text(document_id: str, q: str, db: Session = Depends(get_db)):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    document = _get_document(db, document_id)
    pdf = fitz.open(document.storage_path)
    matches = search_document(pdf, q)
    pdf.close()

    return SearchResponse(query=q, matches=matches)


@router.post("/{document_id}/ocr", response_model=OCRResponse)
def run_document_ocr(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    try:
        return run_ocr(db, document)
    except OCRError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{document_id}/detect-pii", response_model=PIIDetectResponse)
def detect_document_pii(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    return detect_pii(document)


@router.post("/{document_id}/detect-pii/apply")
def apply_pii_suggestions(
    document_id: str,
    payload: PIIBulkRequest,
    db: Session = Depends(get_db),
):
    _get_document(db, document_id)
    created = []
    for suggestion in payload.suggestions:
        redaction = create_redaction(
            db,
            document_id,
            RedactionCreate(
                page_num=suggestion.page_num,
                x0=suggestion.x0,
                y0=suggestion.y0,
                x1=suggestion.x1,
                y1=suggestion.y1,
                source="presidio",
                search_term=suggestion.text,
            ),
        )
        created.append(redaction)
    return {"created": len(created), "redactions": created}


@router.get("/{document_id}/exports/{export_id}/download")
def download_export(document_id: str, export_id: int, db: Session = Depends(get_db)):
    _get_document(db, document_id)
    export_record = db.get(Export, export_id)
    if not export_record or export_record.document_id != document_id:
        raise HTTPException(status_code=404, detail="Export not found")

    path = Path(export_record.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file missing")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
    )
