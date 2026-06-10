import shutil
import uuid
from pathlib import Path

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Document, Page
from backend.services.text_extract import extract_words, is_scanned_document


def ingest_pdf(db: Session, filename: str, content: bytes) -> Document:
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
        pages=page_records,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def get_pdf_path(document: Document) -> Path:
    return Path(document.storage_path)


def rerender_pages(db: Session, document: Document, pdf_path: Path) -> None:
    pdf = fitz.open(str(pdf_path))
    matrix = fitz.Matrix(document.render_scale, document.render_scale)
    pages_dir = settings.storage_dir / "pages" / document.id
    pages_dir.mkdir(parents=True, exist_ok=True)

    for page_record in document.pages:
        page = pdf[page_record.page_num]
        image_path = pages_dir / f"{page_record.page_num}.png"
        pix = page.get_pixmap(matrix=matrix)
        pix.save(str(image_path))
        page_record.image_path = str(image_path)
        words = extract_words(page)
        page_record.word_count = len(words)

    document.page_count = len(pdf)
    document.is_scanned = is_scanned_document(
        [p.word_count for p in document.pages],
        settings.ocr_word_threshold,
    )
    pdf.close()
    db.commit()


def replace_source_pdf(document: Document, new_pdf_path: Path) -> Path:
    """Copy a new PDF over the stored original path (original dir, new content from OCR)."""
    dest = Path(document.storage_path)
    shutil.copy2(new_pdf_path, dest)
    return dest
