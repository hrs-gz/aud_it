from presidio_analyzer import Pattern, PatternRecognizer

CASE_NUMBER_PATTERN = Pattern(
    name="case_number_loose_pattern",
    regex=r"\b(?:Case|Cause|File|Matter|Docket)\s*(?:No\.?|Number|ID|#)?[:\s#\-]*[A-Z0-9][A-Z0-9\-\/]{4,30}\b",
    score=0.70,
)

CASE_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="CASE_NUMBER",
    patterns=[CASE_NUMBER_PATTERN],
    context=["case", "case id", "case number", "matter", "matter id", "matter number", "docket", "file", "cause"],
)
