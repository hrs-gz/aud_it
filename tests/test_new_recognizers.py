import pytest

from tests.conftest import presidio_available

pytestmark = pytest.mark.skipif(
    not presidio_available(), reason="Presidio/spaCy unavailable"
)


@pytest.fixture(scope="module")
def analyzer():
    from backend.presidio.analyzer import _get_analyzer

    return _get_analyzer()


def test_a_number_detected_with_context(analyzer):
    text = "The applicant's Alien Registration Number is A123456789 per USCIS records."
    results = analyzer.analyze(text=text, language="en", entities=["A_NUMBER"], score_threshold=0.5)
    detected = {text[r.start : r.end].strip() for r in results}
    assert "A123456789" in detected


def test_a_number_with_separators(analyzer):
    text = "A-number: A-123-456-789 on file."
    results = analyzer.analyze(text=text, language="en", entities=["A_NUMBER"], score_threshold=0.5)
    assert any("123" in text[r.start : r.end] for r in results)


def test_dob_detected_near_context(analyzer):
    text = "Date of Birth: 04/18/1997. Filed on 01/02/2026."
    results = analyzer.analyze(text=text, language="en", entities=["DOB"], score_threshold=0.5)
    detected = {text[r.start : r.end].strip() for r in results}
    assert "04/18/1997" in detected


def test_plain_date_without_context_below_threshold(analyzer):
    text = "The meeting happened sometime around 03/15/2024 in the main office."
    results = analyzer.analyze(text=text, language="en", entities=["DOB"], score_threshold=0.5)
    assert not results


def test_us_address_manifest_street(analyzer):
    text = "Current address: 742 Maple Ridge Lane, Austin, TX 78701"
    results = analyzer.analyze(text=text, language="en", entities=["US_ADDRESS"], score_threshold=0.5)
    detected = {text[r.start : r.end].strip() for r in results}
    assert "742 Maple Ridge Lane, Austin, TX 78701" in detected


def test_us_address_legal_dataset(analyzer):
    text = "4417 Canal Street, Apt 12B, Houston, TX 77011"
    results = analyzer.analyze(text=text, language="en", entities=["US_ADDRESS"], score_threshold=0.5)
    detected = {text[r.start : r.end].strip() for r in results}
    assert text in detected


def test_us_address_po_box(analyzer):
    text = "P.O. Box 123, Chicago, IL 60601"
    results = analyzer.analyze(text=text, language="en", entities=["US_ADDRESS"], score_threshold=0.5)
    detected = {text[r.start : r.end].strip() for r in results}
    assert text in detected


def test_us_address_city_only_negative(analyzer):
    text = "The meeting happened in Houston, TX on 03/15/2024."
    results = analyzer.analyze(text=text, language="en", entities=["US_ADDRESS"], score_threshold=0.5)
    assert not results


def test_catalog_defaults_include_ner_entities():
    from backend.presidio.analyzer import default_entities, list_recognizers

    catalog = {entry.entity_type for entry in list_recognizers()}
    assert {"A_NUMBER", "DOB", "US_ADDRESS"} <= catalog

    defaults = set(default_entities())
    assert {
        "PERSON",
        "LOCATION",
        "US_SSN",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "A_NUMBER",
        "DOB",
        "US_ADDRESS",
        "USCIS_RECEIPT_NUMBER",
        "CASE_NUMBER",
    } <= defaults
    assert "ORGANIZATION" not in defaults
