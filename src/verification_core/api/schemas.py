"""Public API response models. Field names are part of the public contract (OpenAPI)."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: str


class PublisherOut(BaseModel):
    name: str
    canonical_domain: str | None
    publisher_type: str | None
    country: str | None


class SourceOut(BaseModel):
    id: uuid.UUID
    project: str
    publisher: PublisherOut
    source_type: str
    title: str
    canonical_url: str
    language: str | None
    external_identifier: str | None
    status: str
    current_version_id: uuid.UUID | None


class SourceVersionOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    version_label: str
    retrieved_at: str
    retrieval_method: str
    source_url: str
    final_url: str | None
    tls_host: str | None
    http_status: int | None
    content_type: str
    file_size: int
    sha256: str
    etag: str | None
    last_modified: str | None
    previous_version_id: uuid.UUID | None
    manifest_sha256: str
    signed: bool
    links: dict[str, str]


class ManifestOut(BaseModel):
    manifest: dict[str, Any] = Field(description="The manifest document as signed.")
    manifest_sha256: str = Field(
        description="SHA-256 of the RFC 8785 canonical serialisation of `manifest`."
    )
    canonicalization: Literal["RFC8785"] = "RFC8785"
    signatures: list[dict[str, Any]]


class VerifyHashIn(BaseModel):
    algorithm: Literal["sha256"] = "sha256"
    digest: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_version_id: uuid.UUID | None = None


class VerifyHashOut(BaseModel):
    match: bool
    matches: list[dict[str, Any]]
    note: str


class AuditEventOut(BaseModel):
    sequence: int
    event_type: str
    actor_type: str
    actor_id: str
    object_type: str
    object_id: str
    payload: dict[str, Any]
    previous_event_hash: str
    event_hash: str
    created_at: str


class AuditHeadOut(BaseModel):
    sequence: int
    event_hash: str
    created_at: str
