import json
from datetime import datetime, timezone

import pymupdf as fitz
from sqlalchemy.orm import Session

from backend.database import Export, Redaction
from backend.schemas import VerificationResponse, VerificationResult
from backend.services.text_extract import search_page


def collect_search_terms(redactions: list[Redaction]) -> list[str]:
    terms: set[str] = set()
    for redaction in redactions:
        if redaction.search_term:
            terms.add(redaction.search_term)
        elif redaction.source == "search" and redaction.search_term:
            terms.add(redaction.search_term)
    return sorted(terms)


def verify_export(
    db: Session,
    export_record: Export,
    redactions: list[Redaction],
    extra_terms: list[str] | None = None,
) -> VerificationResponse:
    terms = collect_search_terms(redactions)
    if extra_terms:
        terms = sorted(set(terms) | set(extra_terms))

    results: list[VerificationResult] = []
    doc = fitz.open(export_record.output_path)

    for term in terms:
        found_pages: list[int] = []
        for page_num, page in enumerate(doc):
            if search_page(page, term):
                found_pages.append(page_num)
        results.append(VerificationResult(term=term, found=bool(found_pages), pages=found_pages))

    doc.close()

    passed = all(not result.found for result in results)
    response = VerificationResponse(
        export_id=export_record.id,
        passed=passed,
        results=results,
    )

    export_record.verified_at = datetime.now(timezone.utc)
    export_record.verification_json = json.dumps(response.model_dump(), default=str)
    db.commit()

    return response
