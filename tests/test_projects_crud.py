"""Project CRUD API tests."""

from fastapi.testclient import TestClient

from backend.database import Document, Project, SessionLocal
from backend.main import app
from backend.services.projects import create_project

client = TestClient(app)


def test_create_list_rename_delete_project(db):
    project = create_project(db, "Test matter")
    project_id = project.id

    listed = client.get("/api/projects").json()
    assert any(p["id"] == project_id for p in listed["projects"])

    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["name"] == "Test matter"
    assert detail["step"] == "organize"

    renamed = client.patch(f"/api/projects/{project_id}", json={"name": "Renamed"}).json()
    assert renamed["name"] == "Renamed"

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_upload_document_to_project(db):
    from tests.conftest import ingest_test_pdf

    project = create_project(db, "Upload test")
    pdf_path = __import__("pathlib").Path(__file__).resolve().parent / "redaction_test_pdfs" / "01_text_pii_letter.pdf"
    if not pdf_path.exists():
        import pytest
        pytest.skip("test PDF missing")

    with pdf_path.open("rb") as f:
        res = client.post(
            f"/api/projects/{project.id}/documents",
            files={"files": ("01_text_pii_letter.pdf", f, "application/pdf")},
        )
    assert res.status_code == 200
    body = res.json()
    assert len(body["documents"]) == 1

    pages = client.get(f"/api/projects/{project.id}/pages").json()
    assert len(pages["pages"]) == body["documents"][0]["page_count"]

    docs = client.get(f"/api/documents?project_id={project.id}").json()
    assert len(docs["documents"]) == 1
    assert docs["documents"][0]["project_id"] == project.id


def test_delete_project_removes_documents(db):
    from tests.conftest import ingest_test_pdf

    project = create_project(db, "Delete cascade")
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    doc_id = doc.id
    doc.project_id = project.id
    db.commit()

    client.delete(f"/api/projects/{project.id}")

    with SessionLocal() as session:
        assert session.get(Project, project.id) is None
        assert session.get(Document, doc_id) is None


def test_delete_document_removes_from_project_list(db):
    from backend.services.organize import append_document_pages
    from tests.conftest import ingest_test_pdf

    project = create_project(db, "Doc delete")
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    doc.project_id = project.id
    append_document_pages(db, project, doc)
    db.commit()

    listed = client.get(f"/api/documents?project_id={project.id}").json()
    assert len(listed["documents"]) == 1

    res = client.delete(f"/api/documents/{doc.id}")
    assert res.status_code == 200

    listed = client.get(f"/api/documents?project_id={project.id}").json()
    assert listed["documents"] == []

    with SessionLocal() as session:
        assert session.get(Document, doc.id) is None
