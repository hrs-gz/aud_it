import re

import pytest

from backend.schemas import RuleCreate
from backend.services.rules import build_ad_hoc_recognizers, create_rule, suggest_pattern
from backend.services.rules import test_pattern as run_pattern_test
from tests.conftest import ingest_test_pdf, presidio_available


def test_suggest_pattern_single_example():
    pattern = suggest_pattern(["ACCT-9842-7710-5531"])
    assert re.search(pattern, "ref ACCT-1234-5678-9012 ok")
    assert not re.search(pattern, "ACCT-12-34")


def test_suggest_pattern_merges_counts():
    pattern = suggest_pattern(["A12345678", "A123456789"])
    assert re.search(pattern, "A12345678")
    assert re.search(pattern, "A123456789")
    assert not re.search(pattern, "A1234")


def test_suggest_pattern_mixed_shapes_falls_back_to_alternation():
    pattern = suggest_pattern(["FOO-123", "12/34/5678"])
    assert re.search(pattern, "FOO-123")
    assert re.search(pattern, "12/34/5678")


def test_suggest_pattern_rejects_empty():
    with pytest.raises(ValueError):
        suggest_pattern(["", "  "])


def test_create_rule_validates_regex(db):
    with pytest.raises(ValueError):
        create_rule(
            db,
            RuleCreate(name="bad", entity_type="X", pattern="[unclosed"),
        )


def test_test_pattern_masks_samples(db, manifest):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    result = run_pattern_test(db, r"ACCT-\d{4}-\d{4}-\d{4}", [doc])
    assert result.valid
    assert result.total_matches >= 1
    for sample in result.documents[0].samples:
        assert manifest["account"] not in sample
        assert "\u2022" in sample


def test_test_pattern_invalid_regex(db):
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    result = run_pattern_test(db, "[bad", [doc])
    assert not result.valid
    assert result.error


@pytest.mark.skipif(not presidio_available(), reason="Presidio/spaCy unavailable")
def test_rule_produces_findings_with_default_action(db, manifest):
    from backend.services.batch import detect_one
    from backend.database import Finding, Rule

    rule = create_rule(
        db,
        RuleCreate(
            name="SSN dashes",
            entity_type="SSN_RULE",
            pattern=r"\b\d{3}-\d{2}-\d{4}\b",
            confidence=0.9,
            default_action="approve",
        ),
    )
    doc = ingest_test_pdf(db, "01_text_pii_letter.pdf")
    detect_one(db, doc, entities=["SSN_RULE"], score_threshold=0.5, auto_ocr=False)

    findings = (
        db.query(Finding)
        .filter(Finding.document_id == doc.id, Finding.entity_type == "SSN_RULE")
        .all()
    )
    assert findings
    assert all(f.source == "rule" for f in findings)
    assert all(f.rule_id == rule.id for f in findings)
    # default_action=approve pre-approves rule hits
    assert all(f.status == "approved" for f in findings)

    # cleanup so other tests' enabled-rule list is unaffected
    db.delete(db.get(Rule, rule.id))
    db.commit()


def test_build_ad_hoc_recognizers_skips_invalid(db):
    pytest.importorskip("presidio_analyzer")

    class FakeRule:
        id = 99
        name = "broken"
        entity_type = "X"
        pattern = "[bad"
        confidence = 0.5

    recognizers, entity_types = build_ad_hoc_recognizers([FakeRule()])
    assert recognizers == []
    assert entity_types == []
