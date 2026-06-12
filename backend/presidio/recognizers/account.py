from presidio_analyzer import Pattern, PatternRecognizer

ACCOUNT_PATTERN = Pattern(
    name="account_pattern",
    regex=r"ACCT-\d{4}-\d{4}-\d{4}",
    score=0.85,
)

ACCOUNT_RECOGNIZER = PatternRecognizer(
    supported_entity="ACCOUNT_NUMBER",
    patterns=[ACCOUNT_PATTERN],
    context=["ACCT", "account", "account number"],
)
