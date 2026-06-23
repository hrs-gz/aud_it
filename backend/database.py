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
    event,
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

# Project workflow step values
PROJECT_STEP_ORGANIZE = "organize"
PROJECT_STEP_REDACT = "redact"
PROJECT_STEP_EXPORT = "export"

PROJECT_STEPS = {PROJECT_STEP_ORGANIZE, PROJECT_STEP_REDACT, PROJECT_STEP_EXPORT}


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    step: Mapped[str] = mapped_column(String(32), default=PROJECT_STEP_ORGANIZE)
    organize_action_count: Mapped[int] = mapped_column(Integer, default=0)
    organize_undo_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="project")
    pages: Mapped[list["ProjectPage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectPage.slot_index"
    )
    organize_actions: Mapped[list["OrganizeAction"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="OrganizeAction.seq"
    )


class ProjectPage(Base):
    """Ordered page slot during the organize step."""

    __tablename__ = "project_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    slot_index: Mapped[int] = mapped_column(Integer)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    source_page_num: Mapped[int] = mapped_column(Integer)

    project: Mapped["Project"] = relationship(back_populates="pages")
    source_document: Mapped["Document"] = relationship(back_populates="project_slots")


class OrganizeAction(Base):
    __tablename__ = "organize_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(32))
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped["Project"] = relationship(back_populates="organize_actions")


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
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    is_materialized: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["Project | None"] = relationship(back_populates="documents")
    project_slots: Mapped[list["ProjectPage"]] = relationship(back_populates="source_document")
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


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

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
    "project_id": "VARCHAR(36)",
    "is_materialized": "BOOLEAN DEFAULT 0",
    "archived": "BOOLEAN DEFAULT 0",
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


_PROJECT_MIGRATION_COLUMNS: dict[str, str] = {
    "step": f"VARCHAR(32) DEFAULT '{PROJECT_STEP_ORGANIZE}'",
    "organize_action_count": "INTEGER DEFAULT 0",
    "organize_undo_count": "INTEGER DEFAULT 0",
}


def _ensure_project_columns() -> None:
    """Add new columns to an existing projects table (SQLite create_all won't)."""
    inspector = inspect(engine)
    if "projects" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("projects")}
    with engine.begin() as conn:
        for name, ddl_type in _PROJECT_MIGRATION_COLUMNS.items():
            if name not in existing:
                conn.execute(sql_text(f"ALTER TABLE projects ADD COLUMN {name} {ddl_type}"))


def _backfill_project_pages() -> None:
    """Populate project_pages for upgraded DBs that have linked docs but no slots."""
    import uuid

    from sqlalchemy.orm import Session

    with Session(engine) as db:
        orphans = db.query(Document).filter(Document.project_id.is_(None)).all()
        if orphans:
            legacy = db.query(Project).filter(Project.name == "Legacy project").first()
            if not legacy:
                legacy = Project(
                    id=str(uuid.uuid4()),
                    name="Legacy project",
                    step=PROJECT_STEP_REDACT,
                    organize_action_count=0,
                    organize_undo_count=0,
                )
                db.add(legacy)
                db.flush()
            slot = (
                db.query(ProjectPage)
                .filter(ProjectPage.project_id == legacy.id)
                .count()
            )
            for doc in orphans:
                doc.project_id = legacy.id
                doc.is_materialized = True
                for page in sorted(doc.pages, key=lambda p: p.page_num):
                    db.add(
                        ProjectPage(
                            project_id=legacy.id,
                            slot_index=slot,
                            source_document_id=doc.id,
                            source_page_num=page.page_num,
                        )
                    )
                    slot += 1

        projects = db.query(Project).all()
        for project in projects:
            has_pages = (
                db.query(ProjectPage).filter(ProjectPage.project_id == project.id).count() > 0
            )
            docs = (
                db.query(Document)
                .filter(Document.project_id == project.id, Document.archived.is_(False))
                .order_by(Document.created_at)
                .all()
            )
            if not has_pages and docs:
                slot = 0
                for doc in docs:
                    doc.is_materialized = True
                    for page in sorted(doc.pages, key=lambda p: p.page_num):
                        db.add(
                            ProjectPage(
                                project_id=project.id,
                                slot_index=slot,
                                source_document_id=doc.id,
                                source_page_num=page.page_num,
                            )
                        )
                        slot += 1
                if project.step == PROJECT_STEP_ORGANIZE:
                    project.step = PROJECT_STEP_REDACT
            elif docs and project.step == PROJECT_STEP_ORGANIZE:
                project.step = PROJECT_STEP_REDACT
        db.commit()


def init_db() -> None:
    _ensure_document_columns()
    Base.metadata.create_all(bind=engine)
    _ensure_project_columns()
    _backfill_project_pages()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
