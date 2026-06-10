import shutil
import subprocess
from pathlib import Path

import pymupdf as fitz
import pytesseract
from PIL import Image
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Document
from backend.schemas import OCRResponse, WordBox
from backend.services.pdf_ingest import replace_source_pdf, rerender_pages
from backend.services.text_extract import extract_words, is_scanned_document


class OCRError(Exception):
    pass


def _tesseract_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocrmypdf_available() -> bool:
    return shutil.which("ocrmypdf") is not None


def _ocr_page_with_tesseract(page: fitz.Page, render_scale: float) -> list[WordBox]:
    matrix = fitz.Matrix(render_scale, render_scale)
    pix = page.get_pixmap(matrix=matrix)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words: list[WordBox] = []
    page_rect = page.rect

    for i, text in enumerate(data["text"]):
        if not text or not str(text).strip():
            continue
        conf = int(data["conf"][i])
        if conf < 0:
            continue

        left = data["left"][i]
        top = data["top"][i]
        width = data["width"][i]
        height = data["height"][i]

        x0 = left / render_scale
        y0 = top / render_scale
        x1 = (left + width) / render_scale
        y1 = (top + height) / render_scale

        x0 = max(page_rect.x0, min(x0, page_rect.x1))
        y0 = max(page_rect.y0, min(y0, page_rect.y1))
        x1 = max(page_rect.x0, min(x1, page_rect.x1))
        y1 = max(page_rect.y0, min(y1, page_rect.y1))

        words.append(WordBox(text=str(text).strip(), x0=x0, y0=y0, x1=x1, y1=y1))

    return words


def run_ocr(db: Session, document: Document) -> OCRResponse:
    source_path = Path(document.storage_path)
    work_dir = settings.storage_dir / "work" / document.id
    work_dir.mkdir(parents=True, exist_ok=True)
    work_input = work_dir / "input.pdf"
    work_output = work_dir / "ocr_output.pdf"

    shutil.copy2(source_path, work_input)

    ocr_success = False
    message = ""

    if _ocrmypdf_available():
        try:
            result = subprocess.run(
                [
                    "ocrmypdf",
                    "--force-ocr",
                    "--optimize",
                    "0",
                    str(work_input),
                    str(work_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and work_output.exists():
                replace_source_pdf(document, work_output)
                ocr_success = True
                message = "OCR completed with OCRmyPDF"
            else:
                message = f"OCRmyPDF failed: {result.stderr.strip() or result.stdout.strip()}"
        except Exception as exc:
            message = f"OCRmyPDF error: {exc}"
    else:
        message = "OCRmyPDF not installed; trying Tesseract fallback"

    if not ocr_success:
        if not _tesseract_available():
            raise OCRError(
                "Neither OCRmyPDF nor Tesseract is available. "
                "Install with: brew install tesseract ocrmypdf"
            )

        pdf = fitz.open(str(source_path))
        total_words = 0
        for page_record in document.pages:
            page = pdf[page_record.page_num]
            words = _ocr_page_with_tesseract(page, document.render_scale)
            page_record.word_count = len(words)
            total_words += len(words)
        pdf.close()

        document.is_scanned = is_scanned_document(
            [p.word_count for p in document.pages],
            settings.ocr_word_threshold,
        )
        db.commit()

        return OCRResponse(
            success=True,
            message="OCR completed with Tesseract page fallback (words available via API only)",
            is_scanned=document.is_scanned,
            total_words=total_words,
        )

    rerender_pages(db, document, Path(document.storage_path))
    total_words = sum(p.word_count for p in document.pages)

    return OCRResponse(
        success=True,
        message=message,
        is_scanned=document.is_scanned,
        total_words=total_words,
    )
