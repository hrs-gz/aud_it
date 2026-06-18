from presidio_analyzer import Pattern, PatternRecognizer

I94_NUMBER_PATTERN = Pattern(
    name="i94_number_pattern",
    regex=r"\b(?:I-?94\s*(?:Number|No\.?|#)?[:\s]*)[A-Za-z0-9]{11}\b",
    score=0.75,
)

I94_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="I94_NUMBER",
    patterns=[I94_NUMBER_PATTERN],
    context=["i-94", "i94", "arrival", "departure", "admission", "record"],
)
