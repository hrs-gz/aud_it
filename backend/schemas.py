from datetime import datetime

from pydantic import BaseModel, Field


class PageInfo(BaseModel):
    page_num: int
    word_count: int
    finding_counts: dict[str, int] = Field(default_factory=dict)


class OCRPageError(BaseModel):
    page_num: int
    reason: str


class FindingCounts(BaseModel):
    total: int = 0
    pending: int = 0
    approved: int = 0
    ignored: int = 0
    applied: int = 0
    needs_review: int = 0


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    page_count: int
    is_scanned: bool
    has_ocr: bool
    render_scale: float
    status: str
    status_detail: str | None
    has_applied: bool
    detected_at: datetime | None
    applied_at: datetime | None
    verified_at: datetime | None
    verification_passed: bool | None
    exported_at: datetime | None
    created_at: datetime
    ocr_errors: list[OCRPageError] = Field(default_factory=list)
    finding_counts: FindingCounts = Field(default_factory=FindingCounts)
    pages: list[PageInfo] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class UploadResponse(BaseModel):
    documents: list[DocumentResponse]
    errors: list[str] = Field(default_factory=list)


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


class Rect(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class FindingResponse(BaseModel):
    id: int
    document_id: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    rects: list[Rect]
    entity_type: str
    masked_text: str | None
    confidence: float
    source: str
    rule_id: int | None
    rule_name: str | None = None
    status: str
    value_key: str | None
    created_at: datetime


class FindingsListResponse(BaseModel):
    findings: list[FindingResponse]


class FindingRevealResponse(BaseModel):
    id: int
    text: str | None


class ManualFindingCreate(BaseModel):
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    # "current" = only page_num; explicit list of pages; or "all"
    pages: list[int] | None = None
    all_pages: bool = False


class FindingUpdate(BaseModel):
    status: str | None = None
    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None


class FindingBulkFilter(BaseModel):
    document_ids: list[str] | None = None
    finding_ids: list[int] | None = None
    page_num: int | None = None
    entity_type: str | None = None
    value_key: str | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    status: list[str] | None = None
    source: str | None = None


class FindingBulkRequest(BaseModel):
    action: str  # approve | ignore | reset (back to pending)
    filter: FindingBulkFilter


class FindingBulkResponse(BaseModel):
    updated: int


class SearchFindingsRequest(BaseModel):
    query: str
    document_ids: list[str] | None = None
    entity_type: str = "CUSTOM_SEARCH"


class SearchFindingsResponse(BaseModel):
    created: int
    findings: list[FindingResponse]


class BatchDetectRequest(BaseModel):
    document_ids: list[str]
    entities: list[str] | None = None
    score_threshold: float = 0.5
    auto_ocr: bool = True


class BatchApplyRequest(BaseModel):
    document_ids: list[str]


class BatchVerifyRequest(BaseModel):
    document_ids: list[str]


class BatchExportRequest(BaseModel):
    document_ids: list[str]
    allow_unverified: bool = False


class BatchAcceptedResponse(BaseModel):
    accepted: bool
    document_ids: list[str]
    message: str | None = None


class OCRResponse(BaseModel):
    success: bool
    message: str
    is_scanned: bool
    total_words: int
    errors: list[OCRPageError] = Field(default_factory=list)


class RecognizerCatalogEntry(BaseModel):
    entity_type: str
    label: str
    description: str
    group: str
    custom: bool
    default_enabled: bool


class RecognizerCatalogResponse(BaseModel):
    recognizers: list[RecognizerCatalogEntry]


class RuleCreate(BaseModel):
    name: str
    entity_type: str
    pattern: str
    examples: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    scope: str = "project"
    default_action: str = "review"  # review | approve
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    pattern: str | None = None
    examples: list[str] | None = None
    confidence: float | None = None
    scope: str | None = None
    default_action: str | None = None
    enabled: bool | None = None


class RuleResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    pattern: str
    examples: list[str]
    confidence: float
    scope: str
    default_action: str
    enabled: bool
    created_at: datetime


class RulesListResponse(BaseModel):
    rules: list[RuleResponse]


class RuleSuggestRequest(BaseModel):
    examples: list[str]


class RuleSuggestResponse(BaseModel):
    pattern: str
    matches_examples: bool


class RuleTestRequest(BaseModel):
    pattern: str
    document_ids: list[str]


class RuleTestDocResult(BaseModel):
    document_id: str
    filename: str
    match_count: int
    samples: list[str] = Field(default_factory=list)  # masked


class RuleTestResponse(BaseModel):
    valid: bool
    error: str | None = None
    total_matches: int = 0
    documents: list[RuleTestDocResult] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    name: str
    label: str
    passed: bool
    detail: str | None = None


class ResidualFinding(BaseModel):
    entity_type: str
    masked_text: str
    page_num: int
    confidence: float


class VerificationReport(BaseModel):
    document_id: str
    passed: bool
    checks: list[VerificationCheck]
    residual_findings: list[ResidualFinding] = Field(default_factory=list)
    unresolved_pending: int = 0
    verified_at: datetime | None = None


class ApplyResponse(BaseModel):
    document_id: str
    applied: int
    verification: VerificationReport | None = None


class ExportItemResult(BaseModel):
    document_id: str
    filename: str | None = None
    download_url: str | None = None
    skipped_reason: str | None = None
    verification_passed: bool | None = None


class ExportBatchResponse(BaseModel):
    batch_id: str
    zip_url: str | None = None
    items: list[ExportItemResult]
    warnings: list[str] = Field(default_factory=list)
