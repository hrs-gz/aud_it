"""Hard reset API tests."""

from fastapi.testclient import TestClient

from backend.config import settings
from backend.database import Document, Project, Rule, SessionLocal
from backend.main import app
from backend.services.projects import create_project
from tests.conftest import ingest_test_pdf

client = TestClient(app)


def test_hard_reset_deletes_projects_and_preserves_rules(db):
    create_project(db, "One")
    create_project(db, "Two")
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    doc.project_id = db.query(Project).first().id
    db.commit()

    rule = Rule(
        name="Test rule",
        entity_type="TEST",
        pattern=r"\d+",
        examples_json="[]",
        confidence=0.7,
        scope="project",
        default_action="review",
        enabled=True,
    )
    db.add(rule)
    db.commit()

    res = client.post("/api/admin/hard-reset")
    assert res.status_code == 200
    body = res.json()
    assert body["projects_deleted"] == 2
    assert body["documents_deleted"] >= 1
    assert body["rules_preserved"] is True

    with SessionLocal() as session:
        assert session.query(Project).count() == 0
        assert session.query(Document).count() == 0
        assert session.query(Rule).count() == 1

    for subdir in ("originals", "pages", "work"):
        root = settings.storage_dir / subdir
        if root.exists():
            assert not any(root.iterdir())


def test_hard_reset_sweeps_batch_exports(db):
    batch_dir = settings.storage_dir / "exports" / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    zip_path = batch_dir / "test-batch.zip"
    zip_path.write_bytes(b"fake")

    create_project(db, "Batch sweep")
    res = client.post("/api/admin/hard-reset")
    assert res.status_code == 200
    assert not zip_path.exists()
