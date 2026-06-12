from collections import defaultdict
from datetime import datetime, timezone

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.database import FINDING_APPLIED, FINDING_APPROVED, Document, Finding
from backend.services.findings import rects_of
from backend.services.metadata import strip_all
from backend.services.pdf_ingest import (
    applied_pdf_target,
    current_pdf_path,
    render_redacted_pages,
)


def _flatten_annotations(pdf: fitz.Document) -> None:
    """Bake remaining annotations/widgets into page content so nothing
    interactive (or hidden underneath) survives in the output."""
    if hasattr(pdf, "bake"):
        try:
            pdf.bake(annots=True, widgets=True)
            return
        except Exception:
            pass
    for page in pdf:
        for annot in list(page.annots() or []):
            page.delete_annot(annot)
        for widget in list(page.widgets() or []):
            page.delete_widget(widget)


def apply_redactions(db: Session, document: Document) -> int:
    """Burn approved (and previously applied) findings into a fresh applied
    copy built from the working PDF. True redaction: text is removed, never
    just covered."""
    findings = (
        db.query(Finding)
        .filter(
            Finding.document_id == document.id,
            Finding.status.in_([FINDING_APPROVED, FINDING_APPLIED]),
        )
        .order_by(Finding.page_num, Finding.id)
        .all()
    )

    newly_applied = sum(1 for f in findings if f.status == FINDING_APPROVED)

    pdf = fitz.open(str(current_pdf_path(document)))
    by_page: dict[int, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_page[finding.page_num].append(finding)

    for page_num, page_findings in by_page.items():
        if page_num >= len(pdf):
            continue
        page = pdf[page_num]
        for finding in page_findings:
            for rect in rects_of(finding):
                page.add_redact_annot(
                    fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1), fill=(0, 0, 0)
                )
        page.apply_redactions()

    _flatten_annotations(pdf)
    strip_all(pdf)

    target = applied_pdf_target(document)
    temp_path = target.with_suffix(".tmp.pdf")
    pdf.save(str(temp_path), garbage=4, deflate=True)
    pdf.close()
    temp_path.replace(target)

    for finding in findings:
        finding.status = FINDING_APPLIED

    document.applied_path = str(target)
    document.applied_at = datetime.now(timezone.utc)
    # Any previous verification no longer describes the new applied copy.
    document.verified_at = None
    document.verification_json = None
    db.commit()

    render_redacted_pages(document, target)
    return newly_applied
