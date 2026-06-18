from presidio_analyzer import Pattern, PatternRecognizer

GOVERNMENT_ID_PATTERN = Pattern(
    name="government_id_pattern",
    regex=r"\b(?:Driver'?s\s*License|DL|D/L|State\s*ID|Government\s*ID|ID\s*(?:No\.?|Number|#))[:\s#\-]*[A-Z0-9\-]{5,25}\b",
    score=0.70,
)

GOVERNMENT_ID_RECOGNIZER = PatternRecognizer(
    supported_entity="GOVERNMENT_ID",
    patterns=[GOVERNMENT_ID_PATTERN],
    context=["license", "driver", "state", "government", "identification", "id"],
)
