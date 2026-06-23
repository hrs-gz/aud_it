from presidio_analyzer import Pattern, PatternRecognizer

SCHOOL_ID_PATTERN = Pattern(
    name="school_id_pattern",
    regex=r"\b(?:School\s*ID|Student\s*ID|University\s*ID|Campus\s*ID|Student\s*Number|SID)[:\s#\-]*[A-Z0-9\-]{4,20}\b",
    score=0.70,
)

SCHOOL_ID_RECOGNIZER = PatternRecognizer(
    supported_entity="SCHOOL_ID",
    patterns=[SCHOOL_ID_PATTERN],
    context=["school", "student", "university", "campus", "enrollment", "registrar", "sid"],
)
