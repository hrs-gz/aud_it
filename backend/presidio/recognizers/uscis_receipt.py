from presidio_analyzer import Pattern, PatternRecognizer

USCIS_RECEIPT_PATTERN = Pattern(
    name="uscis_receipt_number_pattern",
    regex=r"\b(?:EAC|WAC|LIN|SRC|NBC|MSC|IOE)[\s\-]?\d{10}\b",
    score=0.90,
)

USCIS_RECEIPT_RECOGNIZER = PatternRecognizer(
    supported_entity="USCIS_RECEIPT_NUMBER",
    patterns=[USCIS_RECEIPT_PATTERN],
    context=["uscis", "receipt", "notice", "case status", "petition", "application"],
)
