import pymupdf as fitz

from backend.database import Document
from backend.schemas import PIIDetectResponse, PIISuggestion
from backend.services.text_extract import extract_words

_analyzer = None
_analyzer_error: str | None = None


def _get_analyzer():
    global _analyzer, _analyzer_error
    if _analyzer is not None:
        return _analyzer
    if _analyzer_error:
        raise RuntimeError(_analyzer_error)

    try:
        from presidio_analyzer import AnalyzerEngine
    except ImportError as exc:
        _analyzer_error = (
            "Presidio not installed. Run: pip install presidio-analyzer presidio-anonymizer spacy "
            "&& python -m spacy download en_core_web_lg"
        )
        raise RuntimeError(_analyzer_error) from exc

    try:
        _analyzer = AnalyzerEngine()
    except Exception as exc:
        _analyzer_error = (
            f"Failed to initialize Presidio analyzer: {exc}. "
            "Install spaCy model: python -m spacy download en_core_web_lg"
        )
        raise RuntimeError(_analyzer_error) from exc

    return _analyzer


def _map_entity_to_words(
    page_text: str,
    words: list,
    start: int,
    end: int,
    page_num: int,
    entity_type: str,
    text: str,
    score: float,
) -> list[PIISuggestion]:
    suggestions: list[PIISuggestion] = []
    cursor = 0
    for word in words:
        idx = page_text.find(word.text, cursor)
        if idx == -1:
            continue
        word_start = idx
        word_end = idx + len(word.text)
        cursor = word_end

        if word_end <= start or word_start >= end:
            continue

        suggestions.append(
            PIISuggestion(
                entity_type=entity_type,
                text=text,
                score=score,
                page_num=page_num,
                x0=word.x0,
                y0=word.y0,
                x1=word.x1,
                y1=word.y1,
            )
        )
    return suggestions


def detect_pii(document: Document, score_threshold: float = 0.5) -> PIIDetectResponse:
    try:
        analyzer = _get_analyzer()
    except RuntimeError as exc:
        return PIIDetectResponse(suggestions=[], message=str(exc))

    pdf = fitz.open(document.storage_path)
    suggestions: list[PIISuggestion] = []

    for page_num, page in enumerate(pdf):
        words = extract_words(page)
        if not words:
            continue

        page_text = " ".join(w.text for w in words)
        results = analyzer.analyze(text=page_text, language="en", score_threshold=score_threshold)

        for result in results:
            entity_text = page_text[result.start : result.end]
            mapped = _map_entity_to_words(
                page_text,
                words,
                result.start,
                result.end,
                page_num,
                result.entity_type,
                entity_text,
                result.score,
            )
            suggestions.extend(mapped)

    pdf.close()

    if not suggestions:
        return PIIDetectResponse(
            suggestions=[],
            message="No PII detected above threshold",
        )

    return PIIDetectResponse(suggestions=suggestions)
