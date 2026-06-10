from datetime import datetime

from pydantic import BaseModel, Field


class PageInfo(BaseModel):
    page_num: int
    word_count: int


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    page_count: int
    is_scanned: bool
    render_scale: float
    status: str
    created_at: datetime
    pages: list[PageInfo]


class WordBox(BaseModel):
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


class WordsResponse(BaseModel):
    page_num: int
    words: list[WordBox]


class SearchMatch(BaseModel):
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float


class SearchResponse(BaseModel):
    query: str
    matches: list[SearchMatch]


class RedactionCreate(BaseModel):
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    source: str = "manual"
    search_term: str | None = None


class RedactionUpdate(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class RedactionResponse(BaseModel):
    id: int
    document_id: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    source: str
    search_term: str | None


class BulkRedactRequest(BaseModel):
    query: str


class BulkRedactResponse(BaseModel):
    created: int
    redactions: list[RedactionResponse]


class ExportResponse(BaseModel):
    export_id: int
    filename: str
    download_url: str
    verification: "VerificationResponse | None" = None


class VerificationResult(BaseModel):
    term: str
    found: bool
    pages: list[int] = Field(default_factory=list)


class VerificationResponse(BaseModel):
    export_id: int
    passed: bool
    results: list[VerificationResult]


class OCRResponse(BaseModel):
    success: bool
    message: str
    is_scanned: bool
    total_words: int


class PIISuggestion(BaseModel):
    entity_type: str
    text: str
    score: float
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float


class PIIDetectResponse(BaseModel):
    suggestions: list[PIISuggestion]
    message: str | None = None


class PIIBulkRequest(BaseModel):
    suggestions: list[PIISuggestion]
