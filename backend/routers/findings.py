import pymupdf as fitz
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import Document, Finding, get_db
from backend.schemas import (
    FindingBulkRequest,
    FindingBulkResponse,
    FindingResponse,
    FindingRevealResponse,
    FindingsListResponse,
    FindingUpdate,
    ManualFindingCreate,
    SearchFindingsRequest,
    SearchFindingsResponse,
)
from backend.services import findings as svc
from backend.services.pdf_ingest import current_pdf_path
from backend.services.text_extract import search_document

router = APIRouter(prefix="/api", tags=["findings"])


def _get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _get_finding(db: Session, finding_id: int) -> Finding:
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.get("/findings", response_model=FindingsListResponse)
def list_findings(
    document_ids: list[str] | None = Query(default=None),
    page: int | None = None,
    entity_type: str | None = None,
    status: list[str] | None = Query(default=None),
    source: str | None = None,
    min_confidence: float | None = None,
    db: Session = Depends(get_db),
):
    findings = svc.list_findings(
        db,
        document_ids=document_ids,
        page_num=page,
        entity_type=entity_type,
        status=status,
        source=source,
        min_confidence=min_confidence,
    )
    return FindingsListResponse(findings=[svc.to_response(f) for f in findings])


@router.get("/findings/{finding_id}/value", response_model=FindingRevealResponse)
def reveal_finding(finding_id: int, db: Session = Depends(get_db)):
    """Explicit reveal of a sensitive value; everything else returns masked text."""
    finding = _get_finding(db, finding_id)
    return FindingRevealResponse(id=finding.id, text=finding.text)


@router.post("/documents/{document_id}/findings", response_model=FindingsListResponse)
def create_manual_finding(
    document_id: str,
    payload: ManualFindingCreate,
    db: Session = Depends(get_db),
):
    document = _get_document(db, document_id)
    created = svc.create_manual_findings(db, document, payload)
    return FindingsListResponse(findings=[svc.to_response(f) for f in created])


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
def update_finding(
    finding_id: int,
    payload: FindingUpdate,
    db: Session = Depends(get_db),
):
    finding = _get_finding(db, finding_id)

    bbox = None
    coords = (payload.x0, payload.y0, payload.x1, payload.y1)
    if all(v is not None for v in coords):
        if finding.source != "manual":
            raise HTTPException(
                status_code=400, detail="Only manual findings can be moved or resized"
            )
        bbox = coords

    try:
        finding = svc.update_finding(db, finding, status=payload.status, bbox=bbox)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.to_response(finding)


@router.delete("/findings/{finding_id}")
def delete_finding(finding_id: int, db: Session = Depends(get_db)):
    finding = _get_finding(db, finding_id)
    if finding.source != "manual":
        raise HTTPException(
            status_code=400,
            detail="Detected findings can't be deleted; ignore them instead",
        )
    db.delete(finding)
    db.commit()
    return {"deleted": True}


@router.post("/findings/bulk", response_model=FindingBulkResponse)
def bulk_findings(payload: FindingBulkRequest, db: Session = Depends(get_db)):
    try:
        updated = svc.bulk_update(db, payload.action, payload.filter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FindingBulkResponse(updated=updated)


@router.post("/findings/search", response_model=SearchFindingsResponse)
def search_to_findings(payload: SearchFindingsRequest, db: Session = Depends(get_db)):
    """'Find similar': turn text-search matches into pending findings across docs."""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    if payload.document_ids:
        documents = [_get_document(db, doc_id) for doc_id in payload.document_ids]
    else:
        documents = db.query(Document).all()

    created = []
    for document in documents:
        pdf = fitz.open(str(current_pdf_path(document)))
        matches = search_document(pdf, query)
        pdf.close()
        created.extend(
            svc.create_search_findings(
                db, document, query, matches, entity_type=payload.entity_type
            )
        )

    return SearchFindingsResponse(
        created=len(created),
        findings=[svc.to_response(f) for f in created],
    )
