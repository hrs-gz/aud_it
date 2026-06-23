from presidio_analyzer import Pattern, PatternRecognizer

EOIR_ID_PATTERN = Pattern(
    name="eoir_id_pattern",
    regex=r"\b(?:EOIR\s*(?:ID|Identification\s*Number|No\.?|Number|#)?)[:\s#\-]*[A-Z0-9\-]{5,20}\b",
    score=0.75,
)

EOIR_ID_RECOGNIZER = PatternRecognizer(
    supported_entity="EOIR_ID",
    patterns=[EOIR_ID_PATTERN],
    context=["eoir", "immigration", "court", "respondent", "attorney", "representative"],
)
