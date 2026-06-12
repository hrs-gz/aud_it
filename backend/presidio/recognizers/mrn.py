from presidio_analyzer import Pattern, PatternRecognizer

MRN_PATTERN = Pattern(
    name="mrn_pattern",
    regex=r"MRN-\d{8}",
    score=0.85,
)

MRN_RECOGNIZER = PatternRecognizer(
    supported_entity="MEDICAL_RECORD_NUMBER",
    patterns=[MRN_PATTERN],
    context=["MRN", "medical record", "patient", "record number"],
)
