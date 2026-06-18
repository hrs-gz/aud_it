import shutil
import uuid
from pathlib import Path

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Document, Page
from backend.services.text_extract import extract_words, is_scanned_document


def ingest_pdf(
    db: Session,
    filename: str,
    content: bytes,
    *,
    project_id: str | None = None,
    is_materialized: bool = False,
) -> Document:
    doc_id = str(uuid.uuid4())
    doc_dir = settings.storage_dir / "originals" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    source_path = doc_dir / "source.pdf"
    source_path.write_bytes(content)

    pdf = fitz.open(stream=content, filetype="pdf")
    page_count = len(pdf)
    render_scale = settings.render_scale

    pages_dir = settings.storage_dir / "pages" / doc_id
    pages_dir.mkdir(parents=True, exist_ok=True)

    word_counts: list[int] = []
    page_records: list[Page] = []

    matrix = fitz.Matrix(render_scale, render_scale)
    for page_num, page in enumerate(pdf):
        image_path = pages_dir / f"{page_num}.png"
        pix = page.get_pixmap(matrix=matrix)
        pix.save(str(image_path))

        words = extract_words(page)
        word_counts.append(len(words))
        page_records.append(
            Page(
                document_id=doc_id,
                page_num=page_num,
                image_path=str(image_path),
                word_count=len(words),
            )
        )

    pdf.close()

    document = Document(
        id=doc_id,
        original_filename=filename,
        storage_path=str(source_path),
        page_count=page_count,
        is_scanned=is_scanned_document(word_counts, settings.ocr_word_threshold),
        render_scale=render_scale,
        status="ready",
        project_id=project_id,
        is_materialized=is_materialized,
        pages=page_records,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def current_pdf_path(document: Document) -> Path:
    """The PDF all text operations should read: the working copy if one exists
    (e.g. after OCR), otherwise the untouched original."""
    if document.working_path and Path(document.working_path).exists():
        return Path(document.working_path)
    return Path(document.storage_path)


def working_pdf_target(document: Document) -> Path:
    work_dir = settings.storage_dir / "work" / document.id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir / "working.pdf"


def applied_pdf_target(document: Document) -> Path:
    work_dir = settings.storage_dir / "work" / document.id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir / "applied.pdf"


def set_working_pdf(document: Document, new_pdf_path: Path) -> Path:
    """Install a new working copy (e.g. OCR output). The original is never touched."""
    dest = working_pdf_target(document)
    if Path(new_pdf_path) != dest:
        shutil.copy2(new_pdf_path, dest)
    document.working_path = str(dest)
    return dest


def delete_document_files(document: Document) -> None:
    for path in (
        settings.storage_dir / "originals" / document.id,
        settings.storage_dir / "pages" / document.id,
        settings.storage_dir / "work" / document.id,
        settings.storage_dir / "exports" / document.id,
    ):
        shutil.rmtree(path, ignore_errors=True)


def rerender_pages(db: Session, document: Document, pdf_path: Path) -> None:
    """Re-render the standard (working) page images and refresh word counts."""
    pdf = fitz.open(str(pdf_path))
    matrix = fitz.Matrix(document.render_scale, document.render_scale)
    pages_dir = settings.storage_dir / "pages" / document.id
    pages_dir.mkdir(parents=True, exist_ok=True)

    for page_record in document.pages:
        if page_record.page_num >= len(pdf):
            continue
        page = pdf[page_record.page_num]
        image_path = pages_dir / f"{page_record.page_num}.png"
        pix = page.get_pixmap(matrix=matrix)
        pix.save(str(image_path))
        page_record.image_path = str(image_path)
        words = extract_words(page)
        page_record.word_count = len(words)

    document.is_scanned = is_scanned_document(
        [p.word_count for p in document.pages],
        settings.ocr_word_threshold,
    )
    pdf.close()
    db.commit()


def render_redacted_pages(document: Document, pdf_path: Path) -> None:
    """Render the applied (redacted) copy as a parallel image set for the
    original/redacted viewer toggle."""
    pdf = fitz.open(str(pdf_path))
    matrix = fitz.Matrix(document.render_scale, document.render_scale)
    pages_dir = settings.storage_dir / "pages" / document.id
    pages_dir.mkdir(parents=True, exist_ok=True)

    for page_num in range(len(pdf)):
        pix = pdf[page_num].get_pixmap(matrix=matrix)
        pix.save(str(pages_dir / f"redacted_{page_num}.png"))
    pdf.close()


def redacted_page_image_path(document: Document, page_num: int) -> Path:
    return settings.storage_dir / "pages" / document.id / f"redacted_{page_num}.png"
