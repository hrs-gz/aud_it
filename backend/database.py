from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text as sql_text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    pass


# Document.status state machine values
DOC_STATUS_READY = "ready"
DOC_STATUS_OCR = "ocr"
DOC_STATUS_DETECTING = "detecting"
DOC_STATUS_APPLYING = "applying"
DOC_STATUS_VERIFYING = "verifying"
DOC_STATUS_EXPORTING = "exporting"
DOC_STATUS_ERROR = "error"

# Finding.status lifecycle values
FINDING_PENDING = "pending"
FINDING_APPROVED = "approved"
FINDING_IGNORED = "ignored"
FINDING_APPLIED = "applied"
FINDING_NEEDS_REVIEW = "needs_review"

FINDING_STATUSES = {
    FINDING_PENDING,
    FINDING_APPROVED,
    FINDING_IGNORED,
    FINDING_APPLIED,
    FINDING_NEEDS_REVIEW,
}


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    render_scale: Mapped[float] = mapped_column(Float, default=2.0)
    status: Mapped[str] = mapped_column(String(32), default=DOC_STATUS_READY)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Working copy (original + OCR text layer). Original at storage_path is never modified.
    working_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Redactions-applied copy, regenerated on each apply.
    applied_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ocr_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    pages: Mapped[list["Page"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    exports: Mapped[list["Export"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_num: Mapped[int] = mapped_column(Integer)
    image_path: Mapped[str] = mapped_column(String(1024))
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped["Document"] = relationship(back_populates="pages")


class Finding(Base):
    """A detected or manually drawn PII occurrence with a staged lifecycle.

    One finding = one entity occurrence on one page. rects_json holds one rect
    per text line the occurrence spans; x0..y1 is the union bounding box.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_num: Mapped[int] = mapped_column(Integer)
    x0: Mapped[float] = mapped_column(Float)
    y0: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    rects_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(32), default="auto")  # auto | rule | search | manual
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=FINDING_PENDING)
    value_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    document: Mapped["Document"] = relationship(back_populates="findings")
    rule: Mapped["Rule | None"] = relationship(back_populates="findings")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))
    entity_type: Mapped[str] = mapped_column(String(64))
    pattern: Mapped[str] = mapped_column(Text)
    examples_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    scope: Mapped[str] = mapped_column(String(32), default="project")
    default_action: Mapped[str] = mapped_column(String(32), default="review")  # review | approve
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    findings: Mapped[list["Finding"]] = relationship(back_populates="rule")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    output_path: Mapped[str] = mapped_column(String(1024))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="exports")


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_DOCUMENT_MIGRATION_COLUMNS: dict[str, str] = {
    "status_detail": "TEXT",
    "working_path": "VARCHAR(1024)",
    "applied_path": "VARCHAR(1024)",
    "ocr_errors_json": "TEXT",
    "detected_at": "DATETIME",
    "applied_at": "DATETIME",
    "verified_at": "DATETIME",
    "verification_json": "TEXT",
    "exported_at": "DATETIME",
}


def _ensure_document_columns() -> None:
    """Add new columns to an existing documents table (SQLite create_all won't)."""
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("documents")}
    with engine.begin() as conn:
        for name, ddl_type in _DOCUMENT_MIGRATION_COLUMNS.items():
            if name not in existing:
                conn.execute(sql_text(f"ALTER TABLE documents ADD COLUMN {name} {ddl_type}"))


def init_db() -> None:
    _ensure_document_columns()
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
