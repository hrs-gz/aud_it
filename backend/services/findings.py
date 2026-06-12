import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.database import (
    FINDING_APPLIED,
    FINDING_APPROVED,
    FINDING_IGNORED,
    FINDING_NEEDS_REVIEW,
    FINDING_PENDING,
    FINDING_STATUSES,
    Document,
    Finding,
    Rule,
)
from backend.schemas import (
    FindingBulkFilter,
    FindingCounts,
    FindingResponse,
    ManualFindingCreate,
    Rect,
)

LOW_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class Occurrence:
    """A raw detection hit before it is persisted as a Finding."""

    page_num: int
    entity_type: str
    text: str
    score: float
    rects: list[tuple[float, float, float, float]]
    rule_id: int | None = None
    source: str = "auto"
    extra: dict = field(default_factory=dict)


def mask_value(text: str | None) -> str | None:
    if text is None:
        return None
    t = " ".join(text.split())
    if not t:
        return None
    if len(t) <= 2:
        return "\u2022" * len(t)
    if len(t) <= 5:
        return t[0] + "\u2022" * (len(t) - 1)
    keep_end = 3 if len(t) >= 8 else 2
    bullets = min(len(t) - 1 - keep_end, 8)
    return t[0] + "\u2022" * bullets + t[-keep_end:]


def value_key_for(text: str | None) -> str | None:
    if text is None:
        return None
    key = " ".join(text.split()).lower()
    return key[:512] if key else None


def rects_of(finding: Finding) -> list[Rect]:
    if finding.rects_json:
        try:
            data = json.loads(finding.rects_json)
            return [Rect(x0=r[0], y0=r[1], x1=r[2], y1=r[3]) for r in data]
        except (ValueError, IndexError, TypeError):
            pass
    return [Rect(x0=finding.x0, y0=finding.y0, x1=finding.x1, y1=finding.y1)]


def to_response(finding: Finding) -> FindingResponse:
    return FindingResponse(
        id=finding.id,
        document_id=finding.document_id,
        page_num=finding.page_num,
        x0=finding.x0,
        y0=finding.y0,
        x1=finding.x1,
        y1=finding.y1,
        rects=rects_of(finding),
        entity_type=finding.entity_type,
        masked_text=mask_value(finding.text),
        confidence=finding.confidence,
        source=finding.source,
        rule_id=finding.rule_id,
        rule_name=finding.rule.name if finding.rule else None,
        status=finding.status,
        value_key=finding.value_key,
        created_at=finding.created_at,
    )


def counts_for_document(db: Session, document_id: str) -> FindingCounts:
    counts = FindingCounts()
    rows = (
        db.query(Finding.status)
        .filter(Finding.document_id == document_id)
        .all()
    )
    for (status,) in rows:
        counts.total += 1
        if status == FINDING_PENDING:
            counts.pending += 1
        elif status == FINDING_APPROVED:
            counts.approved += 1
        elif status == FINDING_IGNORED:
            counts.ignored += 1
        elif status == FINDING_APPLIED:
            counts.applied += 1
        elif status == FINDING_NEEDS_REVIEW:
            counts.needs_review += 1
    return counts


def counts_by_page(db: Session, document_id: str) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {}
    rows = (
        db.query(Finding.page_num, Finding.status)
        .filter(Finding.document_id == document_id)
        .all()
    )
    for page_num, status in rows:
        page = result.setdefault(page_num, {"total": 0})
        page["total"] += 1
        page[status] = page.get(status, 0) + 1
    return result


def list_findings(
    db: Session,
    document_ids: list[str] | None = None,
    page_num: int | None = None,
    entity_type: str | None = None,
    status: list[str] | None = None,
    source: str | None = None,
    min_confidence: float | None = None,
) -> list[Finding]:
    query = db.query(Finding)
    if document_ids:
        query = query.filter(Finding.document_id.in_(document_ids))
    if page_num is not None:
        query = query.filter(Finding.page_num == page_num)
    if entity_type:
        query = query.filter(Finding.entity_type == entity_type)
    if status:
        query = query.filter(Finding.status.in_(status))
    if source:
        query = query.filter(Finding.source == source)
    if min_confidence is not None:
        query = query.filter(Finding.confidence >= min_confidence)
    return query.order_by(Finding.document_id, Finding.page_num, Finding.id).all()


def create_manual_findings(
    db: Session, document: Document, payload: ManualFindingCreate
) -> list[Finding]:
    """Manual boxes are deliberate user actions, so they start approved."""
    if payload.all_pages:
        pages = list(range(document.page_count))
    elif payload.pages:
        pages = sorted({p for p in payload.pages if 0 <= p < document.page_count})
    else:
        pages = [payload.page_num]

    created: list[Finding] = []
    for page_num in pages:
        finding = Finding(
            document_id=document.id,
            page_num=page_num,
            x0=payload.x0,
            y0=payload.y0,
            x1=payload.x1,
            y1=payload.y1,
            rects_json=json.dumps([[payload.x0, payload.y0, payload.x1, payload.y1]]),
            entity_type="MANUAL",
            text=None,
            confidence=1.0,
            source="manual",
            status=FINDING_APPROVED,
        )
        db.add(finding)
        created.append(finding)
    db.commit()
    for finding in created:
        db.refresh(finding)
    return created


def update_finding(
    db: Session,
    finding: Finding,
    status: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> Finding:
    if status is not None:
        if status not in FINDING_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        finding.status = status
    if bbox is not None:
        finding.x0, finding.y0, finding.x1, finding.y1 = bbox
        finding.rects_json = json.dumps([list(bbox)])
    db.commit()
    db.refresh(finding)
    return finding


_BULK_ACTIONS = {
    "approve": FINDING_APPROVED,
    "ignore": FINDING_IGNORED,
    "reset": FINDING_PENDING,
}


def bulk_update(db: Session, action: str, flt: FindingBulkFilter) -> int:
    if action not in _BULK_ACTIONS:
        raise ValueError(f"Invalid action: {action}")
    target_status = _BULK_ACTIONS[action]

    query = db.query(Finding)
    if flt.finding_ids:
        query = query.filter(Finding.id.in_(flt.finding_ids))
    if flt.document_ids:
        query = query.filter(Finding.document_id.in_(flt.document_ids))
    if flt.page_num is not None:
        query = query.filter(Finding.page_num == flt.page_num)
    if flt.entity_type:
        query = query.filter(Finding.entity_type == flt.entity_type)
    if flt.value_key:
        query = query.filter(Finding.value_key == flt.value_key)
    if flt.min_confidence is not None:
        query = query.filter(Finding.confidence >= flt.min_confidence)
    if flt.max_confidence is not None:
        query = query.filter(Finding.confidence <= flt.max_confidence)
    if flt.status:
        query = query.filter(Finding.status.in_(flt.status))
    if flt.source:
        query = query.filter(Finding.source == flt.source)

    # Already-applied findings are burned into the PDF; never silently re-stage them.
    query = query.filter(Finding.status != FINDING_APPLIED)

    updated = 0
    for finding in query.all():
        if finding.status != target_status:
            finding.status = target_status
            updated += 1
    db.commit()
    return updated


def _union_bbox(rects: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[2] for r in rects)
    y1 = max(r[3] for r in rects)
    return x0, y0, x1, y1


def persist_occurrences(
    db: Session,
    document: Document,
    occurrences: list[Occurrence],
    rules_by_id: dict[int, Rule] | None = None,
) -> int:
    """Replace auto/rule findings with fresh detection output, preserving any
    decisions (approved/ignored/applied) the user already made on matching values."""
    rules_by_id = rules_by_id or {}

    existing = (
        db.query(Finding)
        .filter(
            Finding.document_id == document.id,
            Finding.source.in_(["auto", "rule"]),
        )
        .all()
    )
    decided: dict[tuple[int, str, str | None], str] = {}
    for f in existing:
        if f.status in (FINDING_APPROVED, FINDING_IGNORED, FINDING_APPLIED):
            decided[(f.page_num, f.entity_type, f.value_key)] = f.status

    # Applied findings are part of redaction history; keep them. Drop the rest.
    for f in existing:
        if f.status != FINDING_APPLIED:
            db.delete(f)
    db.flush()

    kept_applied = {
        (f.page_num, f.entity_type, f.value_key)
        for f in existing
        if f.status == FINDING_APPLIED
    }

    created = 0
    seen: set[tuple[int, str, str | None, tuple]] = set()
    for occ in occurrences:
        if not occ.rects:
            continue
        value_key = value_key_for(occ.text)
        key = (occ.page_num, occ.entity_type, value_key)
        rounded = tuple(round(v, 1) for r in occ.rects for v in r)
        dedup_key = (*key, rounded)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        if key in kept_applied:
            continue

        status = FINDING_PENDING
        if key in decided:
            status = decided[key]
            if status == FINDING_APPLIED:
                status = FINDING_APPROVED
        elif occ.rule_id is not None:
            rule = rules_by_id.get(occ.rule_id)
            if rule and rule.default_action == "approve":
                status = FINDING_APPROVED
            else:
                status = FINDING_NEEDS_REVIEW
        elif occ.score < LOW_CONFIDENCE_THRESHOLD:
            status = FINDING_NEEDS_REVIEW

        x0, y0, x1, y1 = _union_bbox(occ.rects)
        db.add(
            Finding(
                document_id=document.id,
                page_num=occ.page_num,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                rects_json=json.dumps([list(r) for r in occ.rects]),
                entity_type=occ.entity_type,
                text=occ.text,
                confidence=occ.score,
                source=occ.source,
                rule_id=occ.rule_id,
                status=status,
                value_key=value_key,
            )
        )
        created += 1

    db.commit()
    return created


def create_search_findings(
    db: Session,
    document: Document,
    query: str,
    matches: list,
    entity_type: str = "CUSTOM_SEARCH",
) -> list[Finding]:
    """Persist text-search matches as pending findings (reviewable, never auto-final)."""
    norm_query = " ".join(query.split())
    value_key = value_key_for(norm_query)

    existing_keys = {
        (f.page_num, tuple(round(v, 1) for v in (f.x0, f.y0, f.x1, f.y1)))
        for f in db.query(Finding)
        .filter(Finding.document_id == document.id, Finding.value_key == value_key)
        .all()
    }

    created: list[Finding] = []
    for match in matches:
        key = (match.page_num, tuple(round(v, 1) for v in (match.x0, match.y0, match.x1, match.y1)))
        if key in existing_keys:
            continue
        finding = Finding(
            document_id=document.id,
            page_num=match.page_num,
            x0=match.x0,
            y0=match.y0,
            x1=match.x1,
            y1=match.y1,
            rects_json=json.dumps([[match.x0, match.y0, match.x1, match.y1]]),
            entity_type=entity_type,
            text=norm_query,
            confidence=1.0,
            source="search",
            status=FINDING_PENDING,
            value_key=value_key,
        )
        db.add(finding)
        created.append(finding)
    db.commit()
    for finding in created:
        db.refresh(finding)
    return created
