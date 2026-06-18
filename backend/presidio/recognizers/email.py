from presidio_analyzer import Pattern, PatternRecognizer

EMAIL_PATTERN = Pattern(
    name="email_pattern",
    regex=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    score=0.85,
)

EMAIL_RECOGNIZER = PatternRecognizer(
    supported_entity="EMAIL_ADDRESS",
    patterns=[EMAIL_PATTERN],
    context=["email", "e-mail", "contact", "mail"],
)
