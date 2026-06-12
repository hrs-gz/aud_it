import json
import os
import shutil
import subprocess
from pathlib import Path

import pymupdf as fitz
import pytesseract
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Document
from backend.schemas import OCRPageError, OCRResponse
from backend.services.pdf_ingest import current_pdf_path, rerender_pages, set_working_pdf

OCR_DPI = 300


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


def _find_tessdata() -> str | None:
    if hasattr(fitz, "get_tessdata"):
        try:
            tessdata = fitz.get_tessdata()
            if tessdata:
                return tessdata
        except Exception:
            pass
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).exists():
        return env
    tesseract_bin = shutil.which("tesseract")
    if tesseract_bin:
        candidate = Path(tesseract_bin).resolve().parent.parent / "share" / "tessdata"
        if candidate.exists():
            return str(candidate)
    return None


def get_ocr_errors(document: Document) -> list[OCRPageError]:
    if not document.ocr_errors_json:
        return []
    try:
        data = json.loads(document.ocr_errors_json)
        return [OCRPageError(**entry) for entry in data]
    except (ValueError, TypeError):
        return []


def _run_ocrmypdf(input_path: Path, output_path: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [
            "ocrmypdf",
            "--force-ocr",
            "--optimize",
            "0",
            str(input_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and output_path.exists():
        return True, "OCR completed with OCRmyPDF"
    return False, f"OCRmyPDF failed: {result.stderr.strip() or result.stdout.strip()}"


def _run_pymupdf_tesseract(
    input_path: Path, output_path: Path
) -> tuple[bool, str, list[OCRPageError]]:
    """Build a searchable PDF page-by-page with PyMuPDF's Tesseract OCR.

    Pages that fail keep their original content and are reported as errors,
    so one bad page never sinks the whole document."""
    tessdata = _find_tessdata()
    if tessdata is None:
        return False, "Tesseract language data (tessdata) not found", []

    src = fitz.open(str(input_path))
    out = fitz.open()
    errors: list[OCRPageError] = []
    ocred_pages = 0

    for page_num in range(len(src)):
        try:
            page = src[page_num]
            pix = page.get_pixmap(dpi=OCR_DPI)
            if pix.width < 50 or pix.height < 50:
                raise OCRError("image resolution too low")
            ocr_bytes = pix.pdfocr_tobytes(language="eng", tessdata=tessdata)
            page_pdf = fitz.open("pdf", ocr_bytes)
            out.insert_pdf(page_pdf)
            page_pdf.close()
            ocred_pages += 1
        except Exception as exc:
            errors.append(OCRPageError(page_num=page_num, reason=str(exc)))
            out.insert_pdf(src, from_page=page_num, to_page=page_num)

    src.close()
    if ocred_pages == 0:
        out.close()
        return False, "Tesseract OCR produced no text on any page", errors

    out.save(str(output_path), garbage=3, deflate=True)
    out.close()
    message = f"OCR completed with Tesseract ({ocred_pages} page(s))"
    if errors:
        message += f", {len(errors)} page(s) failed"
    return True, message, errors


def run_ocr(db: Session, document: Document) -> OCRResponse:
    source_path = current_pdf_path(document)
    work_dir = settings.storage_dir / "work" / document.id
    work_dir.mkdir(parents=True, exist_ok=True)
    work_output = work_dir / "ocr_output.pdf"
    if work_output.exists():
        work_output.unlink()

    errors: list[OCRPageError] = []
    ocr_success = False
    message = ""

    if _ocrmypdf_available():
        try:
            ocr_success, message = _run_ocrmypdf(source_path, work_output)
        except Exception as exc:
            message = f"OCRmyPDF error: {exc}"

    if not ocr_success:
        if not _tesseract_available():
            raise OCRError(
                "Neither OCRmyPDF nor Tesseract is available. "
                "Install with: brew install tesseract ocrmypdf"
            )
        fallback_ok, fallback_message, errors = _run_pymupdf_tesseract(
            source_path, work_output
        )
        if not fallback_ok:
            document.ocr_errors_json = json.dumps([e.model_dump() for e in errors])
            db.commit()
            raise OCRError(f"{message + '; ' if message else ''}{fallback_message}")
        message = fallback_message
        ocr_success = True

    set_working_pdf(document, work_output)
    work_output.unlink(missing_ok=True)
    document.ocr_errors_json = json.dumps([e.model_dump() for e in errors]) if errors else None
    db.commit()

    rerender_pages(db, document, current_pdf_path(document))
    total_words = sum(p.word_count for p in document.pages)

    return OCRResponse(
        success=True,
        message=message,
        is_scanned=document.is_scanned,
        total_words=total_words,
        errors=errors,
    )
