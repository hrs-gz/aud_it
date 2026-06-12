import json
import re

from sqlalchemy.orm import Session

from backend.database import Document, Rule
from backend.schemas import (
    RuleCreate,
    RuleResponse,
    RuleTestDocResult,
    RuleTestResponse,
    RuleUpdate,
)
from backend.services.findings import mask_value
from backend.services.pdf_ingest import current_pdf_path
from backend.services.text_extract import extract_words

MAX_TEST_SAMPLES = 5


def to_response(rule: Rule) -> RuleResponse:
    examples: list[str] = []
    if rule.examples_json:
        try:
            examples = json.loads(rule.examples_json)
        except ValueError:
            examples = []
    return RuleResponse(
        id=rule.id,
        name=rule.name,
        entity_type=rule.entity_type,
        pattern=rule.pattern,
        examples=examples,
        confidence=rule.confidence,
        scope=rule.scope,
        default_action=rule.default_action,
        enabled=rule.enabled,
        created_at=rule.created_at,
    )


def list_rules(db: Session, enabled_only: bool = False) -> list[Rule]:
    query = db.query(Rule)
    if enabled_only:
        query = query.filter(Rule.enabled.is_(True))
    return query.order_by(Rule.id).all()


def create_rule(db: Session, payload: RuleCreate) -> Rule:
    _validate_pattern(payload.pattern)
    rule = Rule(
        name=payload.name,
        entity_type=payload.entity_type.strip().upper().replace(" ", "_"),
        pattern=payload.pattern,
        examples_json=json.dumps(payload.examples),
        confidence=payload.confidence,
        scope=payload.scope,
        default_action=payload.default_action,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(db: Session, rule: Rule, payload: RuleUpdate) -> Rule:
    if payload.pattern is not None:
        _validate_pattern(payload.pattern)
        rule.pattern = payload.pattern
    if payload.name is not None:
        rule.name = payload.name
    if payload.entity_type is not None:
        rule.entity_type = payload.entity_type.strip().upper().replace(" ", "_")
    if payload.examples is not None:
        rule.examples_json = json.dumps(payload.examples)
    if payload.confidence is not None:
        rule.confidence = payload.confidence
    if payload.scope is not None:
        rule.scope = payload.scope
    if payload.default_action is not None:
        rule.default_action = payload.default_action
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule: Rule) -> None:
    db.delete(rule)
    db.commit()


def _validate_pattern(pattern: str) -> None:
    if not pattern.strip():
        raise ValueError("Pattern is empty")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc


def build_ad_hoc_recognizers(rules: list[Rule]) -> tuple[list, list[str]]:
    """Turn enabled rules into ad-hoc Presidio recognizers, so rule changes
    never require rebuilding the cached analyzer engine."""
    from presidio_analyzer import Pattern, PatternRecognizer

    from backend.presidio.analyzer import RULE_RECOGNIZER_PREFIX

    recognizers = []
    entity_types: list[str] = []
    for rule in rules:
        try:
            re.compile(rule.pattern)
        except re.error:
            continue
        recognizers.append(
            PatternRecognizer(
                supported_entity=rule.entity_type,
                name=f"{RULE_RECOGNIZER_PREFIX}{rule.id}",
                patterns=[
                    Pattern(name=rule.name, regex=rule.pattern, score=rule.confidence)
                ],
            )
        )
        if rule.entity_type not in entity_types:
            entity_types.append(rule.entity_type)
    return recognizers, entity_types


# --- Pattern suggestion (low-code rule flow) ---------------------------------

_TokenList = list[tuple[str, object]]


def _tokenize(example: str) -> _TokenList:
    """Collapse an example into runs of digit/upper/lower classes and literals."""
    tokens: _TokenList = []
    for ch in example:
        if ch.isdigit():
            kind = "d"
        elif ch.isalpha() and ch.isupper():
            kind = "u"
        elif ch.isalpha():
            kind = "l"
        else:
            kind = "lit"

        if kind == "lit":
            tokens.append(("lit", ch))
        elif tokens and tokens[-1][0] == kind:
            tokens[-1] = (kind, tokens[-1][1] + 1)
        else:
            tokens.append((kind, 1))
    return tokens


_CLASS_REGEX = {"d": r"\d", "u": "[A-Z]", "l": "[a-z]"}


def _shape_of(tokens: _TokenList) -> tuple:
    return tuple((kind, value if kind == "lit" else None) for kind, value in tokens)


def suggest_pattern(examples: list[str]) -> str:
    """Generalize selected example text(s) into a candidate regex."""
    cleaned = [" ".join(e.split()) for e in examples if e.strip()]
    if not cleaned:
        raise ValueError("Provide at least one example")

    token_lists = [_tokenize(e) for e in cleaned]
    shapes = {_shape_of(t) for t in token_lists}

    if len(shapes) > 1:
        # Examples have different structures; fall back to a literal alternation.
        return r"\b(?:" + "|".join(re.escape(e) for e in sorted(set(cleaned))) + r")\b"

    parts: list[str] = []
    base = token_lists[0]
    for idx, (kind, value) in enumerate(base):
        if kind == "lit":
            ch = str(value)
            parts.append(r"\s" if ch == " " else re.escape(ch))
            continue
        counts = {tl[idx][1] for tl in token_lists}
        lo, hi = min(counts), max(counts)
        quant = f"{{{lo}}}" if lo == hi else f"{{{lo},{hi}}}"
        parts.append(_CLASS_REGEX[kind] + quant)

    return r"\b" + "".join(parts) + r"\b"


def test_pattern(db: Session, pattern: str, documents: list[Document]) -> RuleTestResponse:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return RuleTestResponse(valid=False, error=f"Invalid regex: {exc}")

    results: list[RuleTestDocResult] = []
    total = 0
    import pymupdf as fitz

    for document in documents:
        pdf = fitz.open(str(current_pdf_path(document)))
        count = 0
        samples: list[str] = []
        for page in pdf:
            words = extract_words(page)
            if not words:
                continue
            page_text = " ".join(w.text for w in words)
            for match in compiled.finditer(page_text):
                count += 1
                if len(samples) < MAX_TEST_SAMPLES:
                    masked = mask_value(match.group(0))
                    if masked and masked not in samples:
                        samples.append(masked)
        pdf.close()
        total += count
        results.append(
            RuleTestDocResult(
                document_id=document.id,
                filename=document.original_filename,
                match_count=count,
                samples=samples,
            )
        )

    return RuleTestResponse(valid=True, total_matches=total, documents=results)
