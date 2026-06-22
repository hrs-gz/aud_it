"""Hard reset: wipe all projects and files while preserving global rules."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Document, Project
from backend.services.batch import _BUSY_STATUSES
from backend.services.pdf_ingest import delete_document_record
from backend.services.projects import delete_project


def _sweep_batch_exports() -> None:
    batch_dir = settings.storage_dir / "exports" / "batch"
    if not batch_dir.exists():
        return
    for path in batch_dir.glob("*.zip"):
        path.unlink(missing_ok=True)


def _sweep_orphan_storage() -> None:
    for subdir in ("originals", "pages", "work", "exports"):
        root = settings.storage_dir / subdir
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_dir() and subdir != "exports":
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_dir() and child.name != "batch":
                shutil.rmtree(child, ignore_errors=True)


def hard_reset_app(db: Session) -> dict:
    busy = db.query(Document).filter(Document.status.in_(_BUSY_STATUSES)).count()
    if busy:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reset while {busy} document(s) are still processing.",
        )

    projects = db.query(Project).all()
    project_count = len(projects)
    doc_count = db.query(Document).count()

    for project in projects:
        delete_project(db, project)

    orphan_docs = db.query(Document).filter(Document.project_id.is_(None)).all()
    for doc in orphan_docs:
        delete_document_record(db, doc)
    db.commit()

    _sweep_batch_exports()
    _sweep_orphan_storage()

    return {
        "projects_deleted": project_count,
        "documents_deleted": doc_count,
        "rules_preserved": True,
    }
