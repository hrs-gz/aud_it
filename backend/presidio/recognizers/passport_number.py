from presidio_analyzer import Pattern, PatternRecognizer

PASSPORT_NUMBER_PATTERN = Pattern(
    name="passport_number_pattern",
    regex=r"\b(?:Passport|Pass\.?)\s*(?:No\.?|Number|#)?[:\s]*[A-Z0-9]{6,12}\b",
    score=0.70,
)

PASSPORT_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="PASSPORT_NUMBER",
    patterns=[PASSPORT_NUMBER_PATTERN],
    context=["passport", "travel", "identity", "document", "nationality"],
)
