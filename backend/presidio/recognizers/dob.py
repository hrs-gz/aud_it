from presidio_analyzer import Pattern, PatternRecognizer

_MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)

# Base scores sit below the default 0.5 threshold so bare dates don't fire;
# nearby context words (DOB, born, ...) boost matches above it.
DOB_PATTERNS = [
    Pattern(
        name="dob_numeric",
        regex=r"\b(0?[1-9]|1[0-2])[/\-.](0?[1-9]|[12]\d|3[01])[/\-.](19|20)\d{2}\b",
        score=0.4,
    ),
    Pattern(
        name="dob_long_form",
        regex=rf"\b(?:{_MONTHS})\s+(0?[1-9]|[12]\d|3[01]),?\s+(19|20)\d{{2}}\b",
        score=0.4,
    ),
]

DOB_RECOGNIZER = PatternRecognizer(
    supported_entity="DOB",
    patterns=DOB_PATTERNS,
    context=["dob", "d.o.b", "birth", "birthdate", "born", "birthday", "natal"],
)
