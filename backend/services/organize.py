"""Project organize step: page slots, reorder, merge, undo/redo, materialize."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.database import (
    PROJECT_STEP_ORGANIZE,
    PROJECT_STEP_REDACT,
    Document,
    OrganizeAction,
    Project,
    ProjectPage,
)
from backend.services.pdf_ingest import (
    current_pdf_path,
    delete_document_record,
    ingest_pdf,
)

MAX_ORGANIZE_ACTIONS = 50

SlotDict = dict[str, int | str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _touch_project(project: Project) -> None:
    project.updated_at = _now()


def _slots_snapshot(db: Session, project_id: str) -> list[SlotDict]:
    rows = (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project_id)
        .order_by(ProjectPage.slot_index)
        .all()
    )
    return [
        {
            "id": row.id,
            "slot_index": row.slot_index,
            "source_document_id": row.source_document_id,
            "source_page_num": row.source_page_num,
        }
        for row in rows
    ]


def _restore_slots(db: Session, project: Project, snapshot: list[SlotDict]) -> None:
    db.query(ProjectPage).filter(ProjectPage.project_id == project.id).delete()
    db.flush()
    for item in snapshot:
        db.add(
            ProjectPage(
                project_id=project.id,
                slot_index=int(item["slot_index"]),
                source_document_id=str(item["source_document_id"]),
                source_page_num=int(item["source_page_num"]),
            )
        )
    db.flush()


def _push_action(
    db: Session,
    project: Project,
    action_type: str,
    before: list[SlotDict],
    after: list[SlotDict],
) -> None:
    if project.step != PROJECT_STEP_ORGANIZE:
        return

    # Truncate redo branch
    if project.organize_undo_count < project.organize_action_count:
        db.query(OrganizeAction).filter(
            OrganizeAction.project_id == project.id,
            OrganizeAction.seq > project.organize_undo_count,
        ).delete()

    project.organize_undo_count += 1
    project.organize_action_count = project.organize_undo_count

    db.add(
        OrganizeAction(
            project_id=project.id,
            seq=project.organize_undo_count,
            action_type=action_type,
            before_json=json.dumps(before),
            after_json=json.dumps(after),
        )
    )

    # Cap history
    if project.organize_action_count > MAX_ORGANIZE_ACTIONS:
        oldest = (
            db.query(OrganizeAction)
            .filter(OrganizeAction.project_id == project.id)
            .order_by(OrganizeAction.seq)
            .first()
        )
        if oldest:
            db.delete(oldest)
            project.organize_action_count -= 1
            project.organize_undo_count -= 1
            remaining = (
                db.query(OrganizeAction)
                .filter(OrganizeAction.project_id == project.id)
                .order_by(OrganizeAction.seq)
                .all()
            )
            for i, action in enumerate(remaining, start=1):
                action.seq = i
            project.organize_action_count = len(remaining)
            project.organize_undo_count = len(remaining)

    _touch_project(project)


def append_document_pages(db: Session, project: Project, document: Document) -> None:
    """Add page slots for a newly uploaded document."""
    before = _slots_snapshot(db, project.id)
    max_index = (
        db.query(ProjectPage.slot_index)
        .filter(ProjectPage.project_id == project.id)
        .order_by(ProjectPage.slot_index.desc())
        .limit(1)
        .scalar()
    )
    start = (max_index + 1) if max_index is not None else 0

    for page in sorted(document.pages, key=lambda p: p.page_num):
        db.add(
            ProjectPage(
                project_id=project.id,
                slot_index=start,
                source_document_id=document.id,
                source_page_num=page.page_num,
            )
        )
        start += 1
    db.flush()
    after = _slots_snapshot(db, project.id)
    _push_action(db, project, "add_documents", before, after)


def reorder_pages(db: Session, project: Project, slot_ids: list[int]) -> list[ProjectPage]:
    before = _slots_snapshot(db, project.id)
    slots = (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project.id)
        .order_by(ProjectPage.slot_index)
        .all()
    )
    by_id = {s.id: s for s in slots}
    if set(slot_ids) != set(by_id.keys()):
        raise ValueError("slot_ids must match all current page slots")

    for index, slot_id in enumerate(slot_ids):
        by_id[slot_id].slot_index = index
    db.flush()
    after = _slots_snapshot(db, project.id)
    _push_action(db, project, "reorder", before, after)
    return (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project.id)
        .order_by(ProjectPage.slot_index)
        .all()
    )


def delete_page_slot(db: Session, project: Project, slot_id: int) -> None:
    before = _slots_snapshot(db, project.id)
    slot = db.get(ProjectPage, slot_id)
    if not slot or slot.project_id != project.id:
        raise ValueError("Page slot not found")

    removed_index = slot.slot_index
    db.delete(slot)
    db.flush()

    for row in (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project.id, ProjectPage.slot_index > removed_index)
        .all()
    ):
        row.slot_index -= 1
    db.flush()
    after = _slots_snapshot(db, project.id)
    _push_action(db, project, "delete_page", before, after)


def delete_page_slots(db: Session, project: Project, slot_ids: list[int]) -> None:
    before = _slots_snapshot(db, project.id)
    ids_set = set(slot_ids)
    slots = (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project.id)
        .order_by(ProjectPage.slot_index)
        .all()
    )
    remaining = [s for s in slots if s.id not in ids_set]
    if len(remaining) == len(slots):
        raise ValueError("Page slot not found")

    db.query(ProjectPage).filter(ProjectPage.project_id == project.id).delete()
    db.flush()
    for index, slot in enumerate(remaining):
        db.add(
            ProjectPage(
                project_id=project.id,
                slot_index=index,
                source_document_id=slot.source_document_id,
                source_page_num=slot.source_page_num,
            )
        )
    db.flush()
    after = _slots_snapshot(db, project.id)
    _push_action(db, project, "delete_page", before, after)


def merge_documents(db: Session, project: Project) -> None:
    """Concatenate all active project documents (by created_at) into slot order."""
    before = _slots_snapshot(db, project.id)
    docs = (
        db.query(Document)
        .filter(
            Document.project_id == project.id,
            Document.archived.is_(False),
        )
        .order_by(Document.created_at)
        .all()
    )
    if len(docs) < 2:
        raise ValueError("At least two documents are required to merge")

    db.query(ProjectPage).filter(ProjectPage.project_id == project.id).delete()
    db.flush()

    slot_index = 0
    for doc in docs:
        for page in sorted(doc.pages, key=lambda p: p.page_num):
            db.add(
                ProjectPage(
                    project_id=project.id,
                    slot_index=slot_index,
                    source_document_id=doc.id,
                    source_page_num=page.page_num,
                )
            )
            slot_index += 1
    db.flush()
    after = _slots_snapshot(db, project.id)
    _push_action(db, project, "merge_documents", before, after)
    _touch_project(project)


def undo(db: Session, project: Project) -> bool:
    if project.step != PROJECT_STEP_ORGANIZE or project.organize_undo_count <= 0:
        return False
    action = (
        db.query(OrganizeAction)
        .filter(
            OrganizeAction.project_id == project.id,
            OrganizeAction.seq == project.organize_undo_count,
        )
        .first()
    )
    if not action:
        return False
    before = json.loads(action.before_json)
    _restore_slots(db, project, before)
    project.organize_undo_count -= 1
    _touch_project(project)
    return True


def redo(db: Session, project: Project) -> bool:
    if project.step != PROJECT_STEP_ORGANIZE:
        return False
    if project.organize_undo_count >= project.organize_action_count:
        return False
    next_seq = project.organize_undo_count + 1
    action = (
        db.query(OrganizeAction)
        .filter(
            OrganizeAction.project_id == project.id,
            OrganizeAction.seq == next_seq,
        )
        .first()
    )
    if not action:
        return False
    after = json.loads(action.after_json)
    _restore_slots(db, project, after)
    project.organize_undo_count = next_seq
    _touch_project(project)
    return True


def can_undo(project: Project) -> bool:
    return project.step == PROJECT_STEP_ORGANIZE and project.organize_undo_count > 0


def can_redo(project: Project) -> bool:
    return (
        project.step == PROJECT_STEP_ORGANIZE
        and project.organize_undo_count < project.organize_action_count
    )


def materialize_project(db: Session, project: Project) -> Document:
    """Build a single materialized PDF from page slots and advance to redact step."""
    slots = (
        db.query(ProjectPage)
        .filter(ProjectPage.project_id == project.id)
        .order_by(ProjectPage.slot_index)
        .all()
    )
    if not slots:
        raise ValueError("No pages to materialize")

    # Collect source PDFs
    source_docs = (
        db.query(Document)
        .filter(
            Document.project_id == project.id,
            Document.archived.is_(False),
        )
        .order_by(Document.created_at)
        .all()
    )
    if not source_docs:
        raise ValueError("No source documents")

    # If already a single materialized doc with matching pages, just advance
    active = [d for d in source_docs if not d.archived]
    if len(active) == 1 and active[0].is_materialized and len(slots) == active[0].page_count:
        all_match = all(
            s.source_document_id == active[0].id and s.source_page_num == i
            for i, s in enumerate(slots)
        )
        if all_match:
            project.step = PROJECT_STEP_REDACT
            _touch_project(project)
            db.commit()
            return active[0]

    out_pdf = fitz.open()
    for slot in slots:
        doc = db.get(Document, slot.source_document_id)
        if not doc:
            continue
        src = fitz.open(str(current_pdf_path(doc)))
        if slot.source_page_num < 0 or slot.source_page_num >= len(src):
            src.close()
            continue
        out_pdf.insert_pdf(src, from_page=slot.source_page_num, to_page=slot.source_page_num)
        src.close()

    if len(out_pdf) == 0:
        out_pdf.close()
        raise ValueError("Failed to build PDF from page slots")

    # Remove old documents (slots first via delete_document_record)
    for old_doc in source_docs:
        delete_document_record(db, old_doc)
    db.flush()

    # Ingest merged PDF as materialized document
    pdf_bytes = out_pdf.tobytes()
    out_pdf.close()
    first_name = source_docs[0].original_filename
    if len(source_docs) > 1:
        stem = Path(first_name).stem
        merged_name = f"{stem}_merged.pdf"
    else:
        merged_name = first_name

    document = ingest_pdf(
        db,
        merged_name,
        pdf_bytes,
        project_id=project.id,
        is_materialized=True,
        commit=False,
    )

    # Repopulate slots from materialized doc
    for page in sorted(document.pages, key=lambda p: p.page_num):
        db.add(
            ProjectPage(
                project_id=project.id,
                slot_index=page.page_num,
                source_document_id=document.id,
                source_page_num=page.page_num,
            )
        )

    project.step = PROJECT_STEP_REDACT
    project.organize_action_count = 0
    project.organize_undo_count = 0
    db.query(OrganizeAction).filter(OrganizeAction.project_id == project.id).delete()
    _touch_project(project)
    db.commit()
    db.refresh(document)
    return document


def project_summary(db: Session, project: Project) -> dict:
    doc_count = (
        db.query(Document)
        .filter(Document.project_id == project.id, Document.archived.is_(False))
        .count()
    )
    page_count = (
        db.query(ProjectPage).filter(ProjectPage.project_id == project.id).count()
    )
    return {
        "document_count": doc_count,
        "page_count": page_count,
    }
