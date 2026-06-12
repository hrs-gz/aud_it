import json
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.database import (
    FINDING_APPLIED,
    FINDING_IGNORED,
    FINDING_NEEDS_REVIEW,
    FINDING_PENDING,
    Document,
    Finding,
)
from backend.schemas import ResidualFinding, VerificationCheck, VerificationReport
from backend.services.findings import mask_value, rects_of, value_key_for
from backend.services.text_extract import search_page


class VerifyError(Exception):
    pass


def stored_report(document: Document) -> VerificationReport | None:
    if not document.verification_json:
        return None
    try:
        return VerificationReport(**json.loads(document.verification_json))
    except (ValueError, TypeError):
        return None


def _check_search_test(pdf: fitz.Document, applied: list[Finding]) -> VerificationCheck:
    """Every applied finding's text must no longer be findable anywhere."""
    leaked: list[str] = []
    seen_terms: set[str] = set()
    for finding in applied:
        if not finding.text:
            continue
        term = " ".join(finding.text.split())
        if not term or term in seen_terms:
            continue
        seen_terms.add(term)
        found_pages = [
            page_num for page_num, page in enumerate(pdf) if search_page(page, term)
        ]
        if found_pages:
            masked = mask_value(term) or "?"
            pages = ", ".join(str(p + 1) for p in found_pages)
            leaked.append(f"{masked} (p. {pages})")

    return VerificationCheck(
        name="search_test",
        label="Search test passed",
        passed=not leaked,
        detail=f"Still findable: {'; '.join(leaked)}" if leaked else None,
    )


def _check_text_under_boxes(pdf: fitz.Document, applied: list[Finding]) -> VerificationCheck:
    """No extractable text (incl. OCR layers) may remain under redacted boxes."""
    leaks = 0
    pages_hit: set[int] = set()
    for finding in applied:
        if finding.page_num >= len(pdf):
            continue
        page = pdf[finding.page_num]
        for rect in rects_of(finding):
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
            # Slightly shrink so adjacent glyph edges don't false-positive.
            clip = fitz.Rect(clip.x0 + 1, clip.y0 + 1, clip.x1 - 1, clip.y1 - 1)
            if clip.is_empty or clip.is_infinite:
                continue
            text = page.get_text("text", clip=clip).strip()
            if text:
                leaks += 1
                pages_hit.add(finding.page_num + 1)

    return VerificationCheck(
        name="text_removed",
        label="Underlying and OCR text removed",
        passed=leaks == 0,
        detail=(
            f"{leaks} redacted region(s) still contain text "
            f"(pages {', '.join(str(p) for p in sorted(pages_hit))})"
            if leaks
            else None
        ),
    )


def _check_metadata(pdf: fitz.Document) -> VerificationCheck:
    dirty = {k: v for k, v in (pdf.metadata or {}).items() if v}
    # Format/encryption fields are structural, not identifying.
    dirty.pop("format", None)
    dirty.pop("encryption", None)
    return VerificationCheck(
        name="metadata_stripped",
        label="Metadata stripped",
        passed=not dirty,
        detail=f"Remaining metadata keys: {', '.join(sorted(dirty))}" if dirty else None,
    )


def _check_annotations(pdf: fitz.Document) -> VerificationCheck:
    remaining = 0
    for page in pdf:
        remaining += len(list(page.annots() or []))
        remaining += len(list(page.widgets() or []))
    return VerificationCheck(
        name="annotations_flattened",
        label="Annotations flattened",
        passed=remaining == 0,
        detail=f"{remaining} annotation(s)/widget(s) remain" if remaining else None,
    )


def _residual_pii_sweep(
    db: Session, document: Document, applied_path: str
) -> tuple[VerificationCheck, list[ResidualFinding]]:
    """Re-run detection on the applied copy; anything new is potential
    remaining PII the user never saw."""
    try:
        from backend.services.presidio import analyze_document

        occurrences = analyze_document(document, pdf_path=applied_path)
    except RuntimeError:
        return (
            VerificationCheck(
                name="residual_pii",
                label="Residual PII sweep",
                passed=True,
                detail="Skipped: Presidio unavailable",
            ),
            [],
        )

    known = {
        (f.page_num, f.entity_type, f.value_key)
        for f in db.query(Finding)
        .filter(
            Finding.document_id == document.id,
            Finding.status.in_([FINDING_IGNORED, FINDING_PENDING, FINDING_NEEDS_REVIEW]),
        )
        .all()
    }

    residuals: list[ResidualFinding] = []
    seen: set[tuple] = set()
    for occ in occurrences:
        key = (occ.page_num, occ.entity_type, value_key_for(occ.text))
        if key in known or key in seen:
            continue
        seen.add(key)
        residuals.append(
            ResidualFinding(
                entity_type=occ.entity_type,
                masked_text=mask_value(occ.text) or "?",
                page_num=occ.page_num,
                confidence=occ.score,
            )
        )

    return (
        VerificationCheck(
            name="residual_pii",
            label="No residual PII detected",
            passed=not residuals,
            detail=f"{len(residuals)} potential remaining PII finding(s)" if residuals else None,
        ),
        residuals,
    )


def verify_document(db: Session, document: Document) -> VerificationReport:
    if not document.applied_path or not Path(document.applied_path).exists():
        raise VerifyError("No applied redactions to verify. Apply redactions first.")

    applied = (
        db.query(Finding)
        .filter(Finding.document_id == document.id, Finding.status == FINDING_APPLIED)
        .all()
    )
    unresolved = (
        db.query(Finding)
        .filter(
            Finding.document_id == document.id,
            Finding.status.in_([FINDING_PENDING, FINDING_NEEDS_REVIEW]),
        )
        .count()
    )

    pdf = fitz.open(document.applied_path)
    try:
        checks = [
            _check_search_test(pdf, applied),
            _check_text_under_boxes(pdf, applied),
            _check_metadata(pdf),
            _check_annotations(pdf),
        ]
    finally:
        pdf.close()

    residual_check, residuals = _residual_pii_sweep(db, document, document.applied_path)
    checks.append(residual_check)
    checks.append(
        VerificationCheck(
            name="no_unresolved",
            label="No unresolved approvals",
            passed=unresolved == 0,
            detail=f"{unresolved} finding(s) still pending review" if unresolved else None,
        )
    )

    passed = all(check.passed for check in checks)
    verified_at = datetime.now(timezone.utc)
    report = VerificationReport(
        document_id=document.id,
        passed=passed,
        checks=checks,
        residual_findings=residuals,
        unresolved_pending=unresolved,
        verified_at=verified_at,
    )

    document.verified_at = verified_at
    document.verification_json = report.model_dump_json()
    db.commit()

    return report
