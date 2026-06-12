from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import Document, Rule, get_db
from backend.schemas import (
    RuleCreate,
    RuleResponse,
    RulesListResponse,
    RuleSuggestRequest,
    RuleSuggestResponse,
    RuleTestRequest,
    RuleTestResponse,
    RuleUpdate,
)
from backend.services import rules as svc

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _get_rule(db: Session, rule_id: int) -> Rule:
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.get("", response_model=RulesListResponse)
def list_rules(db: Session = Depends(get_db)):
    return RulesListResponse(rules=[svc.to_response(r) for r in svc.list_rules(db)])


@router.post("", response_model=RuleResponse)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    try:
        rule = svc.create_rule(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.to_response(rule)


@router.patch("/{rule_id}", response_model=RuleResponse)
def update_rule(rule_id: int, payload: RuleUpdate, db: Session = Depends(get_db)):
    rule = _get_rule(db, rule_id)
    try:
        rule = svc.update_rule(db, rule, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.to_response(rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = _get_rule(db, rule_id)
    svc.delete_rule(db, rule)
    return {"deleted": True}


@router.post("/suggest", response_model=RuleSuggestResponse)
def suggest_pattern(payload: RuleSuggestRequest):
    import re

    try:
        pattern = svc.suggest_pattern(payload.examples)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    compiled = re.compile(pattern)
    matches_all = all(
        compiled.search(" ".join(e.split())) for e in payload.examples if e.strip()
    )
    return RuleSuggestResponse(pattern=pattern, matches_examples=matches_all)


@router.post("/test", response_model=RuleTestResponse)
def test_pattern(payload: RuleTestRequest, db: Session = Depends(get_db)):
    documents = []
    for doc_id in payload.document_ids:
        document = db.get(Document, doc_id)
        if document:
            documents.append(document)
    if not documents:
        raise HTTPException(status_code=400, detail="No valid documents to test against")

    return svc.test_pattern(db, payload.pattern, documents)
