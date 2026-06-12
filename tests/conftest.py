"""Test config: isolate storage/database in a temp dir BEFORE backend imports."""

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="aud_it_tests_"))
os.environ["AUD_IT_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["AUD_IT_DATA_DIR"] = str(_TMP / "data")
os.environ["AUD_IT_DATABASE_URL"] = f"sqlite:///{_TMP / 'data' / 'test.db'}"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402

PDF_DIR = ROOT / "tests" / "redaction_test_pdfs"
MANIFEST_PATH = PDF_DIR / "README_manifest.json"


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def manifest():
    import json

    return json.loads(MANIFEST_PATH.read_text())["fake_values"]


def ingest_test_pdf(db, name: str):
    from backend.services.pdf_ingest import ingest_pdf

    path = PDF_DIR / name
    if not path.exists():
        pytest.skip(f"Test PDF not found: {path}")
    return ingest_pdf(db, name, path.read_bytes())


def presidio_available() -> bool:
    try:
        from backend.presidio.analyzer import _get_analyzer

        _get_analyzer()
        return True
    except Exception:
        return False


def tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
