"""Import pipeline for one source version (first vertical story, spec ch. 37).

original bytes -> SHA-256 -> write-once storage -> derived text (with transformation record)
-> canonical manifest -> signature -> immutable source_version row -> audit event.

Everything is inserted in one transaction. Nothing existing is updated.
"""

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import __version__, audit
from .extraction import extract
from .fetch import FetchError, Retrieval, host_matches_domain
from .hashing import canonical_json, sha256_hex
from .ids import new_id
from .manifest import build_source_manifest
from .models import (
    Artifact,
    ArtifactType,
    Project,
    Publisher,
    RetrievalMethod,
    Source,
    SourceVersion,
    Transformation,
    utcnow,
)
from .signing import Signer
from .storage import ObjectStore


@dataclass(frozen=True)
class SourceSpec:
    project_slug: str
    publisher_name: str
    source_type: str
    title: str
    canonical_url: str
    project_name: str | None = None
    publisher_domain: str | None = None
    publisher_type: str | None = None
    publisher_country: str | None = None
    language: str | None = None
    external_identifier: str | None = None


@dataclass(frozen=True)
class IngestResult:
    source_version: SourceVersion
    created: bool  # False when the retrieved bytes equal the latest stored version


class IngestError(Exception):
    pass


def _get_or_create_project(session: Session, spec: SourceSpec) -> Project:
    project = session.scalar(select(Project).where(Project.slug == spec.project_slug))
    if project is None:
        project = Project(slug=spec.project_slug, name=spec.project_name or spec.project_slug)
        session.add(project)
        session.flush()
    return project


def _get_or_create_publisher(session: Session, spec: SourceSpec) -> Publisher:
    publisher = session.scalar(select(Publisher).where(Publisher.name == spec.publisher_name))
    if publisher is None:
        publisher = Publisher(
            name=spec.publisher_name,
            canonical_domain=spec.publisher_domain,
            publisher_type=spec.publisher_type,
            country=spec.publisher_country,
        )
        session.add(publisher)
        session.flush()
    elif spec.publisher_domain and publisher.canonical_domain != spec.publisher_domain:
        raise IngestError(
            f"publisher '{publisher.name}' is registered with domain "
            f"'{publisher.canonical_domain}', not '{spec.publisher_domain}'"
        )
    return publisher


def _get_or_create_source(
    session: Session, spec: SourceSpec, project: Project, publisher: Publisher
) -> Source:
    source = session.scalar(
        select(Source).where(
            Source.project_id == project.id, Source.canonical_url == spec.canonical_url
        )
    )
    if source is None:
        source = Source(
            project_id=project.id,
            publisher_id=publisher.id,
            source_type=spec.source_type,
            title=spec.title,
            canonical_url=spec.canonical_url,
            language=spec.language,
            external_identifier=spec.external_identifier,
        )
        session.add(source)
        session.flush()
    elif source.publisher_id != publisher.id:
        raise IngestError("source already registered under a different publisher")
    return source


def latest_version(session: Session, source_id) -> SourceVersion | None:
    return session.scalars(
        select(SourceVersion)
        .where(SourceVersion.source_id == source_id)
        .order_by(SourceVersion.created_at.desc(), SourceVersion.id.desc())
        .limit(1)
    ).first()


def _store_artifact(
    session: Session,
    store: ObjectStore,
    *,
    project: Project,
    artifact_type: ArtifactType,
    media_type: str,
    data: bytes,
    namespace: str,
) -> Artifact:
    artifact = Artifact(
        project_id=project.id,
        artifact_type=artifact_type.value,
        media_type=media_type,
        storage_uri=store.put(namespace, data),
        byte_size=len(data),
        sha256=sha256_hex(data),
    )
    session.add(artifact)
    session.flush()
    return artifact


def ingest(
    session: Session,
    store: ObjectStore,
    spec: SourceSpec,
    retrieval: Retrieval,
    *,
    retrieval_method: RetrievalMethod,
    signer: Signer | None = None,
    code_commit: str = "unknown",
    enforce_publisher_domain: bool = True,
    actor_id: str = "importer",
    version_label: str | None = None,
) -> IngestResult:
    if not retrieval.data:
        raise IngestError("empty document")

    project = _get_or_create_project(session, spec)
    publisher = _get_or_create_publisher(session, spec)

    if (
        retrieval_method == RetrievalMethod.HTTP_FETCH
        and enforce_publisher_domain
        and publisher.canonical_domain
        and not (
            retrieval.tls_host
            and host_matches_domain(retrieval.tls_host, publisher.canonical_domain)
        )
    ):
        raise FetchError(
            f"host '{retrieval.tls_host}' does not belong to publisher domain "
            f"'{publisher.canonical_domain}'"
        )

    source = _get_or_create_source(session, spec, project, publisher)
    digest = sha256_hex(retrieval.data)
    previous = latest_version(session, source.id)

    if previous is not None and previous.sha256 == digest:
        audit.append(
            session,
            event_type="SOURCE_CHECKED_UNCHANGED",
            actor_type="system",
            actor_id=actor_id,
            object_type="source_version",
            object_id=str(previous.id),
            payload={"sha256": digest, "checked_url": retrieval.final_url or retrieval.source_url},
        )
        return IngestResult(previous, created=False)

    importer = {
        "name": "verification-core",
        "version": __version__,
        "code_commit": code_commit,
    }

    original = _store_artifact(
        session,
        store,
        project=project,
        artifact_type=ArtifactType.ORIGINAL_FILE,
        media_type=retrieval.content_type,
        data=retrieval.data,
        namespace="originals",
    )

    derived: list[tuple[Artifact, Transformation]] = []
    started: datetime = utcnow()
    extracted = extract(retrieval.data, retrieval.content_type)
    if extracted is not None:
        text_artifact = _store_artifact(
            session,
            store,
            project=project,
            artifact_type=ArtifactType.EXTRACTED_TEXT,
            media_type=extracted.media_type,
            data=extracted.text.encode("utf-8"),
            namespace="derived",
        )
        transformation = Transformation(
            project_id=project.id,
            transformation_type="TEXT_EXTRACTION",
            software_name=extracted.software_name,
            software_version=extracted.software_version,
            code_commit=code_commit,
            configuration_hash=extracted.configuration_hash,
            started_at=started,
            completed_at=utcnow(),
            status="SUCCEEDED",
            inputs=[original],
            outputs=[text_artifact],
        )
        session.add(transformation)
        session.flush()
        derived.append((text_artifact, transformation))

    count = session.scalar(
        select(func.count()).select_from(SourceVersion).where(SourceVersion.source_id == source.id)
    )
    version = SourceVersion(
        id=new_id(),
        source_id=source.id,
        version_label=version_label or f"v{(count or 0) + 1}",
        retrieved_at=retrieval.retrieved_at,
        retrieval_method=retrieval_method.value,
        source_url=retrieval.source_url,
        final_url=retrieval.final_url,
        tls_host=retrieval.tls_host,
        http_status=retrieval.http_status,
        http_headers=retrieval.headers,
        content_type=retrieval.content_type,
        file_size=len(retrieval.data),
        sha256=digest,
        etag=retrieval.etag,
        last_modified=retrieval.last_modified,
        importer_version=__version__,
        original_artifact_id=original.id,
        previous_version_id=previous.id if previous else None,
    )

    manifest = build_source_manifest(
        project=project,
        publisher=publisher,
        source=source,
        version=version,
        original=original,
        derived=derived,
        importer=importer,
    )
    manifest_bytes = canonical_json(manifest)
    manifest_artifact = _store_artifact(
        session,
        store,
        project=project,
        artifact_type=ArtifactType.MANIFEST,
        media_type="application/json",
        data=manifest_bytes,
        namespace="derived",
    )
    version.manifest_artifact_id = manifest_artifact.id

    if signer is not None:
        signature = signer.sign(manifest_bytes)
        sig_artifact = _store_artifact(
            session,
            store,
            project=project,
            artifact_type=ArtifactType.SIGNATURE,
            media_type="application/json",
            data=json.dumps(signature, sort_keys=True).encode("utf-8"),
            namespace="derived",
        )
        version.signature_artifact_id = sig_artifact.id

    session.add(version)
    session.flush()

    audit.append(
        session,
        event_type="SOURCE_VERSION_CREATED",
        actor_type="system",
        actor_id=actor_id,
        object_type="source_version",
        object_id=str(version.id),
        payload={
            "source_id": str(source.id),
            "sha256": digest,
            "manifest_sha256": manifest_artifact.sha256,
            "retrieval_method": retrieval_method.value,
            "previous_version_id": str(previous.id) if previous else None,
        },
    )
    return IngestResult(version, created=True)
