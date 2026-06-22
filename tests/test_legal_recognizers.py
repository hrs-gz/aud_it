import pytest

from tests.conftest import presidio_available

pytestmark = pytest.mark.skipif(
    not presidio_available(), reason="Presidio/spaCy unavailable"
)


@pytest.fixture(scope="module")
def analyzer():
    from backend.presidio.analyzer import _get_analyzer

    return _get_analyzer()


def test_eoir_id_with_context(analyzer):
    text = "EOIR ID: EOIR-AB12-34567 for the respondent."
    results = analyzer.analyze(text=text, language="en", entities=["EOIR_ID"], score_threshold=0.5)
    assert results


def test_i94_number_with_context(analyzer):
    text = "I-94 Number: 12345678901 admission record."
    results = analyzer.analyze(text=text, language="en", entities=["I94_NUMBER"], score_threshold=0.5)
    detected = {text[r.start : r.end] for r in results}
    assert any("12345678901" in value for value in detected)


def test_hearing_number_with_context(analyzer):
    text = "Hearing No. HRG-2026-00481 scheduled for review."
    results = analyzer.analyze(
        text=text, language="en", entities=["HEARING_NUMBER"], score_threshold=0.5
    )
    assert results


def test_school_id_with_context(analyzer):
    text = "Student ID: STU-88421-09 on enrollment form."
    results = analyzer.analyze(text=text, language="en", entities=["SCHOOL_ID"], score_threshold=0.5)
    assert results
