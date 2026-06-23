from presidio_analyzer import Pattern, PatternRecognizer

HEARING_NUMBER_PATTERN = Pattern(
    name="hearing_number_pattern",
    regex=r"\b(?:Hearing|Hrng)\s*(?:No\.?|Number|ID|#)[:\s#\-]*[A-Z0-9\-]{4,30}\b",
    score=0.65,
)

HEARING_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="HEARING_NUMBER",
    patterns=[HEARING_NUMBER_PATTERN],
    context=["hearing", "court", "calendar", "notice", "master", "individual", "merits"],
)
