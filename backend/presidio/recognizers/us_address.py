import re
from typing import Iterable

import usaddress
from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts
from usaddress import RepeatedLabelError

_US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|"
    "MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|"
    "SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)

_STREET_START = re.compile(r"\b\d{1,6}\s+")
_STREET_WINDOW = re.compile(
    rf"^\d{{1,6}}\s+"
    rf"(?:[A-Za-z0-9#\-'.]+[\s,]*){{1,10}}"
    rf"(?:{_US_STATES})\b"
    rf"(?:\s+\d{{5}}(?:-\d{{4}})?)?",
    re.IGNORECASE,
)
_MAX_STREET_WINDOW = 140

_PO_BOX_CANDIDATE = re.compile(
    rf"\bP\.?\s*O\.?\s*Box\s+\d+[\s,]*"
    rf"(?:[A-Za-z0-9#\-'.]+[\s,]*){{0,6}}"
    rf"(?:{_US_STATES})\b"
    rf"(?:\s+\d{{5}}(?:-\d{{4}})?)?",
    re.IGNORECASE,
)

_ADDRESS_LABEL = re.compile(
    r"(?:current|mailing|former|prior|home|residential|street|physical|"
    r"employer|clinic|court|shelter)?\s*address\s*:?\s*",
    re.IGNORECASE,
)

_ACCEPTED_TYPES = frozenset({"Street Address", "PO Box"})
_ADDRESS_START_LABELS = frozenset({"AddressNumber", "USPSBoxType", "BuildingName"})
_ADDRESS_END_LABELS = frozenset({"ZipCode", "StateName", "PlaceName"})
_BASE_SCORE = 0.80
_ZIP_BONUS = 0.05
_MAX_SCORE = 0.90
# usaddress is expensive on long spans; skip pathological candidates.
_MAX_CANDIDATE_LEN = 220


def _score_address(components: dict[str, str], addr_type: str) -> float | None:
    if addr_type not in _ACCEPTED_TYPES:
        return None

    if addr_type == "Street Address":
        required = ("AddressNumber", "StreetName", "PlaceName", "StateName")
    else:
        required = ("USPSBoxType", "PlaceName", "StateName")

    if not all(components.get(field) for field in required):
        return None

    score = _BASE_SCORE
    if components.get("ZipCode"):
        score += _ZIP_BONUS
    return min(score, _MAX_SCORE)


def _refine_span(candidate: str, candidate_start: int) -> tuple[int, int, float] | None:
    leading = len(candidate) - len(candidate.lstrip(" \t,."))
    cleaned = candidate.strip(" \t,;.")
    if not cleaned or len(cleaned) > _MAX_CANDIDATE_LEN:
        return None

    try:
        parsed = usaddress.parse(cleaned)
        components, addr_type = usaddress.tag(cleaned)
    except RepeatedLabelError:
        return None

    score = _score_address(components, addr_type)
    if score is None:
        return None

    start_token_idx: int | None = None
    end_token_idx: int | None = None
    for i, (_, label) in enumerate(parsed):
        if label in _ADDRESS_START_LABELS and start_token_idx is None:
            start_token_idx = i
        if label in _ADDRESS_END_LABELS:
            end_token_idx = i

    base = candidate_start + leading
    if start_token_idx is None or end_token_idx is None:
        return base, base + len(cleaned), score

    pos = 0
    char_start: int | None = None
    char_end: int | None = None
    for i, (token, _) in enumerate(parsed):
        idx = cleaned.find(token, pos)
        if idx == -1:
            continue
        if i == start_token_idx:
            char_start = idx
        if i == end_token_idx:
            char_end = idx + len(token)
        pos = idx + len(token)

    if char_start is None or char_end is None:
        return base, base + len(cleaned), score

    return base + char_start, base + char_end, score


def _iter_street_candidates(text: str) -> Iterable[tuple[int, int, str]]:
    """Scan for street-number starts, then match inside a short window.

    The previous whole-text regex could backtrack catastrophically on dense
  legal prose with multiple state abbreviations."""
    for start_match in _STREET_START.finditer(text):
        window = text[start_match.start() : start_match.start() + _MAX_STREET_WINDOW]
        match = _STREET_WINDOW.match(window)
        if not match:
            continue
        span = match.group()
        yield start_match.start(), start_match.start() + len(span), span


def _iter_label_candidates(text: str) -> Iterable[tuple[int, int, str]]:
    for match in _ADDRESS_LABEL.finditer(text):
        start = match.end()
        remainder = text[start:]
        end = len(text)
        for sep in (".", ";", "\n"):
            idx = remainder.find(sep)
            if idx != -1:
                end = min(end, start + idx)
        yield start, end, text[start:end]


def _dedupe_results(
    hits: list[tuple[int, int, float, str]],
) -> list[tuple[int, int, float, str]]:
    if not hits:
        return []

    hits.sort(key=lambda item: (item[0], item[1] - item[0]))
    kept: list[tuple[int, int, float, str]] = []

    for start, end, score, span_text in hits:
        replaced = False
        for i, (k_start, k_end, k_score, k_text) in enumerate(kept):
            if start >= k_start and end <= k_end:
                if (end - start) < (k_end - k_start) or score > k_score:
                    kept[i] = (start, end, score, span_text)
                replaced = True
                break
            if k_start >= start and k_end <= end:
                if (k_end - k_start) < (end - start) or score >= k_score:
                    kept.pop(i)
                else:
                    replaced = True
                    break
        if not replaced:
            kept.append((start, end, score, span_text))

    return kept


class UsAddressRecognizer(EntityRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entities=["US_ADDRESS"],
            name="UsAddressRecognizer",
            supported_language="en",
            context=[
                "address",
                "mailing",
                "residence",
                "street",
                "apt",
                "suite",
                "located",
                "city",
            ],
        )

    def load(self) -> None:
        pass

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: NlpArtifacts | None = None,
    ) -> list[RecognizerResult]:
        if "US_ADDRESS" not in entities:
            return []

        candidates: list[tuple[int, int, str]] = []

        for start, end, span in _iter_street_candidates(text):
            candidates.append((start, end, span))

        for match in _PO_BOX_CANDIDATE.finditer(text):
            candidates.append((match.start(), match.end(), match.group()))

        for start, end, fragment in _iter_label_candidates(text):
            candidates.append((start, end, fragment))

        hits: list[tuple[int, int, float, str]] = []
        seen_spans: set[tuple[int, int]] = set()

        for raw_start, _raw_end, raw_text in candidates:
            refined = _refine_span(raw_text, raw_start)
            if refined is None:
                continue

            start, end, score = refined
            span_key = (start, end)
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)
            hits.append((start, end, score, text[start:end]))

        results: list[RecognizerResult] = []
        for start, end, score, _ in _dedupe_results(hits):
            explanation = AnalysisExplanation(
                recognizer=self.name,
                original_score=score,
                textual_explanation="Parsed as US address by usaddress",
            )
            results.append(
                RecognizerResult(
                    entity_type="US_ADDRESS",
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=explanation,
                    recognition_metadata={
                        RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                        RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                    },
                )
            )

        return results


US_ADDRESS_RECOGNIZER = UsAddressRecognizer()
