"""Relational data model of the verification core.

Immutability rule (ADR-0003): rows in ``artifacts``, ``source_versions``, ``transformations``,
``transformation_inputs``, ``transformation_outputs`` and ``audit_events`` are insert-only.
The application never updates or deletes them, and the PostgreSQL migration installs
triggers that reject UPDATE and DELETE on these tables.

This module contains no domain logic of any specific project (e.g. Bilaterale III).
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .ids import new_id


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON}


class ArtifactType(enum.StrEnum):
    ORIGINAL_FILE = "ORIGINAL_FILE"
    EXTRACTED_TEXT = "EXTRACTED_TEXT"
    OCR_TEXT = "OCR_TEXT"
    MARKDOWN = "MARKDOWN"
    STRUCTURED_JSON = "STRUCTURED_JSON"
    CHUNK_SET = "CHUNK_SET"
    MANIFEST = "MANIFEST"
    SIGNATURE = "SIGNATURE"
    REPORT = "REPORT"


class RetrievalMethod(enum.StrEnum):
    HTTP_FETCH = "HTTP_FETCH"  # fetched by the importer directly from the official URL
    MANUAL_UPLOAD = "MANUAL_UPLOAD"  # supplied by an editor; weaker provenance, flagged as such


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Publisher(Base):
    __tablename__ = "publishers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    canonical_domain: Mapped[str | None] = mapped_column(String(253))
    publisher_type: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(2))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Source(Base):
    """A logical source, independent of any concrete retrieved version."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("project_id", "canonical_url"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    publisher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publishers.id"))
    source_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(1000))
    canonical_url: Mapped[str] = mapped_column(String(2000))
    language: Mapped[str | None] = mapped_column(String(10))
    external_identifier: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship()
    publisher: Mapped[Publisher] = relationship()


class Artifact(Base):
    """Any stored byte object: original file, derived text, manifest, signature."""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    artifact_type: Mapped[str] = mapped_column(String(30))
    media_type: Mapped[str] = mapped_column(String(200))
    storage_uri: Mapped[str] = mapped_column(String(500))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceVersion(Base):
    """One immutable retrieval of a source. A changed file always yields a new row."""

    __tablename__ = "source_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(100))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieval_method: Mapped[str] = mapped_column(String(30))
    source_url: Mapped[str] = mapped_column(String(2000))
    final_url: Mapped[str | None] = mapped_column(String(2000))
    tls_host: Mapped[str | None] = mapped_column(String(253))
    http_status: Mapped[int | None] = mapped_column(Integer)
    http_headers: Mapped[dict[str, Any]] = mapped_column(default=dict)
    content_type: Mapped[str] = mapped_column(String(200))
    file_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(100))
    importer_version: Mapped[str] = mapped_column(String(100))
    original_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"))
    manifest_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"))
    signature_artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[Source] = relationship()
    original: Mapped[Artifact] = relationship(foreign_keys=[original_artifact_id])
    manifest: Mapped[Artifact] = relationship(foreign_keys=[manifest_artifact_id])
    signature: Mapped[Artifact | None] = relationship(foreign_keys=[signature_artifact_id])


transformation_inputs = Table(
    "transformation_inputs",
    Base.metadata,
    Column("transformation_id", ForeignKey("transformations.id"), primary_key=True),
    Column("artifact_id", ForeignKey("artifacts.id"), primary_key=True),
)

transformation_outputs = Table(
    "transformation_outputs",
    Base.metadata,
    Column("transformation_id", ForeignKey("transformations.id"), primary_key=True),
    Column("artifact_id", ForeignKey("artifacts.id"), primary_key=True),
)


class Transformation(Base):
    """How artifacts were derived from other artifacts (W3C PROV: Activity)."""

    __tablename__ = "transformations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    transformation_type: Mapped[str] = mapped_column(String(50))
    software_name: Mapped[str] = mapped_column(String(200))
    software_version: Mapped[str] = mapped_column(String(100))
    code_commit: Mapped[str] = mapped_column(String(100))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))

    inputs: Mapped[list[Artifact]] = relationship(secondary=transformation_inputs)
    outputs: Mapped[list[Artifact]] = relationship(secondary=transformation_outputs)


class AuditEvent(Base):
    """Hash-chained audit log. Each event commits to its predecessor (ADR-0005)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    sequence: Mapped[int] = mapped_column(BigInteger, unique=True)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_type: Mapped[str] = mapped_column(String(50))
    actor_id: Mapped[str] = mapped_column(String(200))
    object_type: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str] = mapped_column(String(100))
    event_payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    previous_event_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


IMMUTABLE_TABLES = (
    "artifacts",
    "source_versions",
    "transformations",
    "transformation_inputs",
    "transformation_outputs",
    "audit_events",
)
