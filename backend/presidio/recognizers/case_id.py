from presidio_analyzer import Pattern, PatternRecognizer

CASE_ID_PATTERN = Pattern(
    name="case_id_pattern",
    regex=r"CASE-\d{4}-\d{5}",
    score=0.85,
)

CASE_ID_RECOGNIZER = PatternRecognizer(
    supported_entity="CASE_ID",
    patterns=[CASE_ID_PATTERN],
    context=["CASE", "case", "case number", "case id"],
)
