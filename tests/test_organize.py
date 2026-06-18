"""Organize step: reorder, delete, merge, undo/redo, advance."""

from fastapi.testclient import TestClient

from backend.database import Project
from backend.main import app
from backend.services.projects import create_project
from tests.conftest import PDF_DIR, ingest_test_pdf

client = TestClient(app)


def _upload_two_pdfs(project_id: str):
    files = []
    for name in ("01_text_pii_letter.pdf", "02_ssn_table.pdf"):
        path = PDF_DIR / name
        if not path.exists():
            import pytest
            pytest.skip(f"Missing {name}")
        files.append(("files", (name, path.read_bytes(), "application/pdf")))
    return client.post(f"/api/projects/{project_id}/documents", files=files)


def test_reorder_and_undo(db):
    project = create_project(db, "Reorder test")
    res = _upload_two_pdfs(project.id)
    assert res.status_code == 200

    pages = client.get(f"/api/projects/{project.id}/pages").json()["pages"]
    assert len(pages) >= 2
    ids = [p["id"] for p in pages]
    swapped = [ids[1], ids[0], *ids[2:]]

    reordered = client.patch(
        f"/api/projects/{project.id}/pages/reorder",
        json={"slot_ids": swapped},
    )
    assert reordered.status_code == 200
    new_pages = reordered.json()["pages"]
    assert new_pages[0]["id"] == ids[1]
    assert reordered.json()["can_undo"] is True

    undone = client.post(f"/api/projects/{project.id}/organize/undo")
    assert undone.status_code == 200
    restored = undone.json()["pages"]
    assert restored[0]["id"] == ids[0]
    assert undone.json()["can_redo"] is True

    redone = client.post(f"/api/projects/{project.id}/organize/redo")
    assert redone.status_code == 200
    assert redone.json()["pages"][0]["id"] == ids[1]


def test_delete_pages(db):
    project = create_project(db, "Delete pages")
    res = _upload_two_pdfs(project.id)
    assert res.status_code == 200

    pages = client.get(f"/api/projects/{project.id}/pages").json()["pages"]
    slot_id = pages[0]["id"]
    deleted = client.post(
        f"/api/projects/{project.id}/pages/delete",
        json={"slot_ids": [slot_id]},
    )
    assert deleted.status_code == 200
    assert len(deleted.json()["pages"]) == len(pages) - 1


def test_merge_documents(db):
    project = create_project(db, "Merge test")
    res = _upload_two_pdfs(project.id)
    assert res.status_code == 200

    merged = client.post(f"/api/projects/{project.id}/merge-documents")
    assert merged.status_code == 200
    pages = merged.json()["pages"]
    doc_count = client.get(f"/api/documents?project_id={project.id}").json()
    assert len(doc_count["documents"]) == 2
    assert len(pages) == sum(d["page_count"] for d in doc_count["documents"])


def test_advance_materializes(db):
    from backend.services.organize import append_document_pages

    project = create_project(db, "Advance test")
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    doc.project_id = project.id
    db.commit()
    db.refresh(doc)

    append_document_pages(db, project, doc)
    db.commit()

    advanced = client.post(f"/api/projects/{project.id}/advance")
    assert advanced.status_code == 200
    body = advanced.json()
    assert body["project"]["step"] == "redact"
    assert body["document"]["is_materialized"] is True

    db.expire_all()
    refreshed = db.get(Project, project.id)
    assert refreshed.step == "redact"
