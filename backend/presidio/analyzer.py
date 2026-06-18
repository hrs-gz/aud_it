import threading

import pymupdf as fitz

from backend.database import Document
from backend.presidio.catalog import RecognizerCatalogEntry, build_catalog_from_registry
from backend.presidio.registry import build_analyzer
from backend.schemas import WordBox
from backend.services.findings import Occurrence
from backend.services.pdf_ingest import current_pdf_path
from backend.services.text_extract import extract_words

_analyzer = None
_analyzer_error: str | None = None
_catalog: list[RecognizerCatalogEntry] | None = None
_analyzer_lock = threading.Lock()

RULE_RECOGNIZER_PREFIX = "rule:"


def _get_analyzer():
    global _analyzer, _analyzer_error, _catalog
    if _analyzer is not None:
        return _analyzer
    if _analyzer_error:
        raise RuntimeError(_analyzer_error)

    try:
        from presidio_analyzer import AnalyzerEngine  # noqa: F401
    except ImportError as exc:
        _analyzer_error = (
            "Presidio not installed. Run: pip install presidio-analyzer presidio-anonymizer spacy "
            "&& python -m spacy download en_core_web_lg"
        )
        raise RuntimeError(_analyzer_error) from exc

    try:
        _analyzer = build_analyzer()
        _catalog = build_catalog_from_registry(_analyzer.get_supported_entities())
    except Exception as exc:
        _analyzer_error = (
            f"Failed to initialize Presidio analyzer: {exc}. "
            "Install spaCy model: python -m spacy download en_core_web_lg"
        )
        raise RuntimeError(_analyzer_error) from exc

    return _analyzer


def list_recognizers() -> list[RecognizerCatalogEntry]:
    try:
        _get_analyzer()
    except RuntimeError as exc:
        return [
            RecognizerCatalogEntry(
                entity_type="_error",
                label="Presidio unavailable",
                description=str(exc),
                group="custom",
                custom=True,
                default_enabled=False,
            )
        ]

    assert _catalog is not None
    return _catalog


def default_entities() -> list[str]:
    catalog = list_recognizers()
    return [
        entry.entity_type
        for entry in catalog
        if entry.default_enabled and entry.entity_type != "_error"
    ]


def _word_offsets(words: list[WordBox]) -> list[tuple[int, int]]:
    """Char offsets of each word within the space-joined page text."""
    offsets: list[tuple[int, int]] = []
    pos = 0
    for word in words:
        offsets.append((pos, pos + len(word.text)))
        pos += len(word.text) + 1
    return offsets


def _merge_words_into_line_rects(
    boxes: list[WordBox],
) -> list[tuple[float, float, float, float]]:
    """Merge word boxes into one rect per text line so a multi-word entity
    becomes a clean horizontal bar instead of n separate boxes."""
    rects: list[tuple[float, float, float, float]] = []
    current: list[float] | None = None
    for box in boxes:
        if current is None:
            current = [box.x0, box.y0, box.x1, box.y1]
            continue
        cur_height = current[3] - current[1]
        same_line = abs(((box.y0 + box.y1) / 2) - ((current[1] + current[3]) / 2)) < max(
            cur_height, box.y1 - box.y0
        ) * 0.6
        if same_line and box.x0 >= current[0] - 2:
            current[0] = min(current[0], box.x0)
            current[1] = min(current[1], box.y0)
            current[2] = max(current[2], box.x1)
            current[3] = max(current[3], box.y1)
        else:
            rects.append(tuple(current))
            current = [box.x0, box.y0, box.x1, box.y1]
    if current is not None:
        rects.append(tuple(current))
    return rects


def analyze_document(
    document: Document,
    entities: list[str] | None = None,
    score_threshold: float = 0.5,
    ad_hoc_recognizers: list | None = None,
    rule_entity_types: list[str] | None = None,
    pdf_path: str | None = None,
) -> list[Occurrence]:
    """Run Presidio over each page and return entity occurrences mapped to
    PDF coordinates. Raises RuntimeError if Presidio is unavailable."""
    analyzer = _get_analyzer()

    target_entities = list(entities) if entities else default_entities()
    for extra in rule_entity_types or []:
        if extra not in target_entities:
            target_entities.append(extra)
    if not target_entities:
        return []

    pdf = fitz.open(pdf_path or str(current_pdf_path(document)))
    occurrences: list[Occurrence] = []

    try:
        with _analyzer_lock:
            for page_num, page in enumerate(pdf):
                words = extract_words(page)
                if not words:
                    continue

                page_text = " ".join(w.text for w in words)
                offsets = _word_offsets(words)

                results = analyzer.analyze(
                    text=page_text,
                    language="en",
                    entities=target_entities,
                    score_threshold=score_threshold,
                    ad_hoc_recognizers=ad_hoc_recognizers or None,
                )

                for result in results:
                    hit_words = [
                        words[i]
                        for i, (w_start, w_end) in enumerate(offsets)
                        if w_end > result.start and w_start < result.end
                    ]
                    if not hit_words:
                        continue

                    rule_id: int | None = None
                    source = "auto"
                    metadata = result.recognition_metadata or {}
                    recognizer_name = metadata.get("recognizer_name", "")
                    if recognizer_name.startswith(RULE_RECOGNIZER_PREFIX):
                        source = "rule"
                        try:
                            rule_id = int(recognizer_name[len(RULE_RECOGNIZER_PREFIX):])
                        except ValueError:
                            rule_id = None

                    occurrences.append(
                        Occurrence(
                            page_num=page_num,
                            entity_type=result.entity_type,
                            text=page_text[result.start : result.end],
                            score=result.score,
                            rects=_merge_words_into_line_rects(hit_words),
                            rule_id=rule_id,
                            source=source,
                        )
                    )
    finally:
        pdf.close()

    return occurrences
