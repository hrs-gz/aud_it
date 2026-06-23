from presidio_analyzer import Pattern, PatternRecognizer

HEARING_ACCESS_CODE_PATTERN = Pattern(
    name="hearing_access_code_pattern",
    regex=r"\b(?:Access\s*Code|Passcode|Meeting\s*ID|Webex\s*ID|Zoom\s*ID)[:\s#\-]*[A-Z0-9\- ]{4,30}\b",
    score=0.65,
)

HEARING_ACCESS_CODE_RECOGNIZER = PatternRecognizer(
    supported_entity="HEARING_ACCESS_CODE",
    patterns=[HEARING_ACCESS_CODE_PATTERN],
    context=["hearing", "webex", "zoom", "meeting", "access", "passcode", "code"],
)
