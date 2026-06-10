import pymupdf as fitz

from backend.schemas import SearchMatch, WordBox


def _prepare_page(page: fitz.Page) -> None:
    fitz.TOOLS.set_small_glyph_heights(True)


def extract_words(page: fitz.Page) -> list[WordBox]:
    _prepare_page(page)
    words: list[WordBox] = []
    for item in page.get_text("words"):
        x0, y0, x1, y1, text, *_ = item
        if text.strip():
            words.append(WordBox(text=text, x0=x0, y0=y0, x1=x1, y1=y1))
    return words


def search_page(page: fitz.Page, query: str) -> list[tuple[float, float, float, float]]:
    _prepare_page(page)
    rects: list[tuple[float, float, float, float]] = []
    for rect in page.search_for(query):
        rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
    return rects


def search_document(doc: fitz.Document, query: str) -> list[SearchMatch]:
    matches: list[SearchMatch] = []
    for page_num, page in enumerate(doc):
        for x0, y0, x1, y1 in search_page(page, query):
            matches.append(
                SearchMatch(page_num=page_num, x0=x0, y0=y0, x1=x1, y1=y1)
            )
    return matches


def is_scanned_document(word_counts: list[int], threshold: int) -> bool:
    if not word_counts:
        return True
    avg = sum(word_counts) / len(word_counts)
    return avg < threshold
