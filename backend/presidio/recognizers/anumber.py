from presidio_analyzer import Pattern, PatternRecognizer

# Alien Registration Numbers: "A" followed by 8 or 9 digits, with optional
# separators (A123456789, A-123-456-789, A 123 456 78).
A_NUMBER_PATTERN = Pattern(
    name="a_number_pattern",
    regex=r"\bA[\s#:\-]*(?:\d[\s\-]*){7,9}\b",
    score=0.6,
)

A_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="A_NUMBER",
    patterns=[A_NUMBER_PATTERN],
    context=["alien", "a-number", "anumber", "uscis", "registration", "immigration", "a#"],
)
