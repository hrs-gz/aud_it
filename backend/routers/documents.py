from pathlib import Path

import pymupdf as fitz
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import Document, Export, Project, get_db
from backend.schemas import (
    DocumentListResponse,
    DocumentResponse,
    OCRResponse,
    PageInfo,
    SearchResponse,
    UploadResponse,
    WordsResponse,
)
from backend.services.findings import counts_by_page, counts_for_document
from backend.services.ocr import OCRError, get_ocr_errors, run_ocr
from backend.services.pdf_ingest import (
    current_pdf_path,
    delete_document_record,
    ingest_pdf,
    redacted_page_image_path,
)
from backend.services.organize import append_document_pages
from backend.services.text_extract import extract_words, search_document
from backend.services.verify import stored_report

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def document_response(db: Session, document: Document, include_pages: bool = True) -> DocumentResponse:
    counts = counts_for_document(db, document.id)
    report = stored_report(document)

    pages: list[PageInfo] = []
    if include_pages:
        page_counts = counts_by_page(db, document.id)
        pages = [
            PageInfo(
                page_num=p.page_num,
                word_count=p.word_count,
                finding_counts=page_counts.get(p.page_num, {}),
            )
            for p in sorted(document.pages, key=lambda p: p.page_num)
        ]

    return DocumentResponse(
        id=document.id,
        original_filename=document.original_filename,
        page_count=document.page_count,
        is_scanned=document.is_scanned,
        has_ocr=bool(document.working_path),
        render_scale=document.render_scale,
        status=document.status,
        status_detail=document.status_detail,
        has_applied=bool(document.applied_path and Path(document.applied_path).exists()),
        detected_at=document.detected_at,
        applied_at=document.applied_at,
        verified_at=document.verified_at,
        verification_passed=report.passed if report else None,
        exported_at=document.exported_at,
        created_at=document.created_at,
        project_id=document.project_id,
        is_materialized=document.is_materialized,
        archived=document.archived,
        ocr_errors=get_ocr_errors(document),
        finding_counts=counts,
        pages=pages,
    )


@router.post("", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    project = None
    if project_id:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    documents: list[DocumentResponse] = []
    errors: list[str] = []

    for file in files:
        name = file.filename or "unnamed"
        if not name.lower().endswith(".pdf"):
            errors.append(f"{name}: only PDF files are supported")
            continue
        content = await file.read()
        if not content:
            errors.append(f"{name}: empty file")
            continue
        try:
            document = ingest_pdf(
                db,
                name,
                content,
                project_id=project_id,
                is_materialized=not project_id,
            )
            if project:
                append_document_pages(db, project, document)
                db.commit()
                db.refresh(document)
            documents.append(document_response(db, document))
        except Exception:
            errors.append(f"{name}: failed to ingest (not a valid PDF?)")

    if not documents and errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return UploadResponse(documents=documents, errors=errors)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    project_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if project_id:
        query = query.filter(
            Document.project_id == project_id,
            Document.archived.is_(False),
        )
    documents = query.order_by(Document.created_at).all()
    return DocumentListResponse(
        documents=[document_response(db, d) for d in documents]
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    return document_response(db, _get_document(db, document_id))


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    delete_document_record(db, document)
    db.commit()
    return {"deleted": True}


@router.get("/{document_id}/pages/{page_num}/image")
def get_page_image(
    document_id: str,
    page_num: int,
    version: str = "original",
    db: Session = Depends(get_db),
):
    document = _get_document(db, document_id)
    if page_num < 0 or page_num >= document.page_count:
        raise HTTPException(status_code=404, detail="Page not found")

    if version == "redacted":
        path = redacted_page_image_path(document, page_num)
        if not path.exists():
            raise HTTPException(status_code=404, detail="No redacted render for this page")
        return FileResponse(path, media_type="image/png")

    page = next((p for p in document.pages if p.page_num == page_num), None)
    if not page or not Path(page.image_path).exists():
        raise HTTPException(status_code=404, detail="Page image not found")

    return FileResponse(page.image_path, media_type="image/png")


@router.get("/{document_id}/pages/{page_num}/words", response_model=WordsResponse)
def get_page_words(document_id: str, page_num: int, db: Session = Depends(get_db)):
    document = _get_document(db, document_id)
    if page_num < 0 or page_num >= document.page_count:
        raise HTTPException(status_code=404, detail="Page not found")

    pdf_path = current_pdf_path(document)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Source PDF not found")

    pdf = fitz.open(str(pdf_path))
    words = extract_words(pdf[page_num])
    pdf.close()

    return WordsResponse(page_num=page_num, words=words)


@router.get("/{document_id}/search", response_model=SearchResponse)
def search_document_text(document_id: str, q: str, db: Session = Depends(get_db)):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    document = _get_document(db, document_id)
    pdf = fitz.open(str(current_pdf_path(document)))
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
