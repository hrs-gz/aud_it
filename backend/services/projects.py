"""Project CRUD helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.database import PROJECT_STEP_ORGANIZE, Document, Project
from backend.services.organize import can_redo, can_undo, project_summary


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_project(db: Session, name: str = "Untitled project") -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        step=PROJECT_STEP_ORGANIZE,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def delete_project(db: Session, project: Project) -> None:
    docs = db.query(Document).filter(Document.project_id == project.id).all()
    from backend.services.pdf_ingest import delete_document_files

    for doc in docs:
        delete_document_files(doc)
        db.delete(doc)
    db.delete(project)
    db.commit()


def project_to_response(db: Session, project: Project) -> dict:
    summary = project_summary(db, project)
    return {
        "id": project.id,
        "name": project.name,
        "step": project.step,
        "document_count": summary["document_count"],
        "page_count": summary["page_count"],
        "can_undo": can_undo(project),
        "can_redo": can_redo(project),
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def project_to_summary(db: Session, project: Project) -> dict:
    summary = project_summary(db, project)
    return {
        "id": project.id,
        "name": project.name,
        "step": project.step,
        "document_count": summary["document_count"],
        "page_count": summary["page_count"],
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }
