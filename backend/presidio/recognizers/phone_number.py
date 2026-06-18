from presidio_analyzer import Pattern, PatternRecognizer

PHONE_NUMBER_PATTERN = Pattern(
    name="phone_number_us_pattern",
    regex=r"\b(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}\b",
    score=0.70,
)

PHONE_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="PHONE_NUMBER",
    patterns=[PHONE_NUMBER_PATTERN],
    context=["phone", "mobile", "cell", "telephone", "tel", "call", "contact"],
)
