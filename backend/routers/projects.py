from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.database import Document, Project, ProjectPage, get_db
from backend.routers.documents import document_response
from backend.schemas import (
    ProjectAdvanceResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectPageSlot,
    ProjectPagesDelete,
    ProjectPagesReorder,
    ProjectPagesResponse,
    ProjectResponse,
    ProjectSummary,
    ProjectUpdate,
    UploadResponse,
)
from backend.services.organize import (
    append_document_pages,
    can_redo,
    can_undo,
    delete_page_slots,
    materialize_project,
    merge_documents,
    redo,
    reorder_pages,
    undo,
)
from backend.services.pdf_ingest import ingest_pdf
from backend.services.projects import (
    create_project,
    delete_project,
    get_project,
    project_to_response,
    project_to_summary,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require_project(db: Session, project_id: str) -> Project:
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _page_slots(db: Session, project: Project) -> list[ProjectPageSlot]:
    rows = (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project.id)
        .order_by(ProjectPage.slot_index)
        .all()
    )
    slots: list[ProjectPageSlot] = []
    for row in rows:
        doc = db.get(Document, row.source_document_id)
        filename = doc.original_filename if doc else "unknown"
        slots.append(
            ProjectPageSlot(
                id=row.id,
                slot_index=row.slot_index,
                source_document_id=row.source_document_id,
                source_page_num=row.source_page_num,
                source_filename=filename,
                thumbnail_url=(
                    f"/api/documents/{row.source_document_id}/pages/"
                    f"{row.source_page_num}/image?version=original"
                ),
            )
        )
    return slots


@router.get("", response_model=ProjectListResponse)
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return ProjectListResponse(
        projects=[ProjectSummary(**project_to_summary(db, p)) for p in projects]
    )


@router.post("", response_model=ProjectResponse)
def create_new_project(payload: ProjectCreate | None = None, db: Session = Depends(get_db)):
    name = payload.name if payload else "Untitled project"
    project = create_project(db, name)
    return ProjectResponse(**project_to_response(db, project))


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project_detail(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    return ProjectResponse(**project_to_response(db, project))


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)
):
    project = _require_project(db, project_id)
    if payload.name is not None:
        project.name = payload.name.strip() or project.name
    if payload.step is not None:
        project.step = payload.step
    from datetime import datetime, timezone

    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return ProjectResponse(**project_to_response(db, project))


@router.delete("/{project_id}")
def remove_project(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    delete_project(db, project)
    return {"deleted": True}


@router.post("/{project_id}/documents", response_model=UploadResponse)
async def upload_project_documents(
    project_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    project = _require_project(db, project_id)
    documents = []
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
                project_id=project.id,
                is_materialized=False,
            )
            append_document_pages(db, project, document)
            db.commit()
            db.refresh(document)
            documents.append(document_response(db, document))
        except Exception:
            errors.append(f"{name}: failed to ingest (not a valid PDF?)")

    if not documents and errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return UploadResponse(documents=documents, errors=errors)


@router.get("/{project_id}/pages", response_model=ProjectPagesResponse)
def list_project_pages(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.patch("/{project_id}/pages/reorder", response_model=ProjectPagesResponse)
def reorder_project_pages(
    project_id: str, payload: ProjectPagesReorder, db: Session = Depends(get_db)
):
    project = _require_project(db, project_id)
    try:
        reorder_pages(db, project, payload.slot_ids)
        db.commit()
        db.refresh(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.delete("/{project_id}/pages/{slot_id}", response_model=ProjectPagesResponse)
def delete_project_page(slot_id: int, project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    try:
        delete_page_slots(db, project, [slot_id])
        db.commit()
        db.refresh(project)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.post("/{project_id}/pages/delete", response_model=ProjectPagesResponse)
def delete_project_pages_batch(
    project_id: str, payload: ProjectPagesDelete, db: Session = Depends(get_db)
):
    project = _require_project(db, project_id)
    try:
        delete_page_slots(db, project, payload.slot_ids)
        db.commit()
        db.refresh(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.post("/{project_id}/merge-documents", response_model=ProjectPagesResponse)
def merge_project_documents(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    try:
        merge_documents(db, project)
        db.commit()
        db.refresh(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.post("/{project_id}/organize/undo", response_model=ProjectPagesResponse)
def organize_undo(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not undo(db, project):
        raise HTTPException(status_code=400, detail="Nothing to undo")
    db.commit()
    db.refresh(project)
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.post("/{project_id}/organize/redo", response_model=ProjectPagesResponse)
def organize_redo(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    if not redo(db, project):
        raise HTTPException(status_code=400, detail="Nothing to redo")
    db.commit()
    db.refresh(project)
    return ProjectPagesResponse(
        pages=_page_slots(db, project),
        can_undo=can_undo(project),
        can_redo=can_redo(project),
    )


@router.post("/{project_id}/advance", response_model=ProjectAdvanceResponse)
def advance_project(project_id: str, db: Session = Depends(get_db)):
    project = _require_project(db, project_id)
    try:
        document = materialize_project(db, project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(project)
    return ProjectAdvanceResponse(
        project=ProjectResponse(**project_to_response(db, project)),
        document=document_response(db, document),
    )
