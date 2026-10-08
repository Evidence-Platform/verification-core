"""Public, read-only verification API (spec ch. 18).

Everything a third party needs to verify a source version is reachable without an account:
original bytes, manifest, signatures, public keys, provenance and the audit chain.
"""

import json
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import __version__
from ..db import iso
from ..hashing import sha256_hex
from ..ingest import latest_version
from ..models import (
    AuditEvent,
    Project,
    Source,
    SourceVersion,
    Transformation,
    transformation_inputs,
)
from ..settings_runtime import Runtime, build_runtime
from ..storage import ObjectStore
from .schemas import (
    AuditEventOut,
    AuditHeadOut,
    ManifestOut,
    ProjectOut,
    PublisherOut,
    SourceOut,
    SourceVersionOut,
    VerifyHashIn,
    VerifyHashOut,
)

API = "/api/v1"


def create_app(runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or build_runtime()
    app = FastAPI(
        title="Verification Core API",
        version=__version__,
        description=(
            "Public read API of an externally verifiable information platform. "
            "Don't trust us, verify us: every original, manifest and signature is retrievable "
            "and every hash can be recomputed independently."
        ),
        license_info={"name": "Apache-2.0", "identifier": "Apache-2.0"},
    )
    app.state.runtime = runtime
    # Read-only public data: any origin may read it (external verifiers, browser tools).
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"])

    def get_session(request: Request) -> Iterator[Session]:
        factory: sessionmaker[Session] = request.app.state.runtime.sessionmaker
        with factory() as session:
            yield session

    def get_store(request: Request) -> ObjectStore:
        return request.app.state.runtime.store

    SessionDep = Annotated[Session, Depends(get_session)]
    StoreDep = Annotated[ObjectStore, Depends(get_store)]

    def _version_or_404(session: Session, version_id: uuid.UUID) -> SourceVersion:
        version = session.get(SourceVersion, version_id)
        if version is None:
            raise HTTPException(404, "source version not found")
        return version

    def _version_out(v: SourceVersion) -> SourceVersionOut:
        base = f"{API}/source-versions/{v.id}"
        return SourceVersionOut(
            id=v.id,
            source_id=v.source_id,
            version_label=v.version_label,
            retrieved_at=iso(v.retrieved_at),
            retrieval_method=v.retrieval_method,
            source_url=v.source_url,
            final_url=v.final_url,
            tls_host=v.tls_host,
            http_status=v.http_status,
            content_type=v.content_type,
            file_size=v.file_size,
            sha256=v.sha256,
            etag=v.etag,
            last_modified=v.last_modified,
            previous_version_id=v.previous_version_id,
            manifest_sha256=v.manifest.sha256,
            signed=v.signature_artifact_id is not None,
            links={
                "self": base,
                "original": f"{base}/original",
                "manifest": f"{base}/manifest",
                "provenance": f"{base}/provenance",
            },
        )

    def _source_out(session: Session, s: Source) -> SourceOut:
        current = latest_version(session, s.id)
        return SourceOut(
            id=s.id,
            project=s.project.slug,
            publisher=PublisherOut(
                name=s.publisher.name,
                canonical_domain=s.publisher.canonical_domain,
                publisher_type=s.publisher.publisher_type,
                country=s.publisher.country,
            ),
            source_type=s.source_type,
            title=s.title,
            canonical_url=s.canonical_url,
            language=s.language,
            external_identifier=s.external_identifier,
            status=s.status,
            current_version_id=current.id if current else None,
        )

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get(f"{API}/projects", response_model=list[ProjectOut])
    def list_projects(session: SessionDep):
        return [
            ProjectOut(
                id=p.id, slug=p.slug, name=p.name, description=p.description, status=p.status
            )
            for p in session.scalars(select(Project).order_by(Project.slug))
        ]

    @app.get(f"{API}/projects/{{slug}}/sources", response_model=list[SourceOut])
    def list_sources(slug: str, session: SessionDep):
        project = session.scalar(select(Project).where(Project.slug == slug))
        if project is None:
            raise HTTPException(404, "project not found")
        sources = session.scalars(
            select(Source).where(Source.project_id == project.id).order_by(Source.title)
        )
        return [_source_out(session, s) for s in sources]

    @app.get(f"{API}/sources/{{source_id}}", response_model=SourceOut)
    def get_source(source_id: uuid.UUID, session: SessionDep):
        source = session.get(Source, source_id)
        if source is None:
            raise HTTPException(404, "source not found")
        return _source_out(session, source)

    @app.get(f"{API}/sources/{{source_id}}/versions", response_model=list[SourceVersionOut])
    def list_versions(source_id: uuid.UUID, session: SessionDep):
        if session.get(Source, source_id) is None:
            raise HTTPException(404, "source not found")
        versions = session.scalars(
            select(SourceVersion)
            .where(SourceVersion.source_id == source_id)
            .order_by(SourceVersion.created_at, SourceVersion.id)
        )
        return [_version_out(v) for v in versions]

    @app.get(f"{API}/source-versions/{{version_id}}", response_model=SourceVersionOut)
    def get_version(version_id: uuid.UUID, session: SessionDep):
        return _version_out(_version_or_404(session, version_id))

    @app.get(f"{API}/source-versions/{{version_id}}/original")
    def get_original(version_id: uuid.UUID, session: SessionDep, store: StoreDep):
        version = _version_or_404(session, version_id)
        data = store.get(version.original.storage_uri)
        if sha256_hex(data) != version.sha256:  # never serve bytes that do not match
            raise HTTPException(500, "stored original failed integrity check")
        return Response(
            content=data,
            media_type=version.original.media_type,
            headers={
                "X-Content-SHA256": version.sha256,
                "Content-Disposition": f'attachment; filename="{version.sha256}"',
            },
        )

    @app.get(f"{API}/source-versions/{{version_id}}/manifest", response_model=ManifestOut)
    def get_manifest(version_id: uuid.UUID, session: SessionDep, store: StoreDep):
        version = _version_or_404(session, version_id)
        manifest_bytes = store.get(version.manifest.storage_uri)
        signatures = []
        if version.signature is not None:
            signatures.append(json.loads(store.get(version.signature.storage_uri)))
        return ManifestOut(
            manifest=json.loads(manifest_bytes),
            manifest_sha256=sha256_hex(manifest_bytes),
            signatures=signatures,
        )

    @app.get(f"{API}/source-versions/{{version_id}}/provenance")
    def get_provenance(version_id: uuid.UUID, session: SessionDep):
        """Provenance chain in a W3C PROV inspired structure (entity, activity, agent)."""
        version = _version_or_404(session, version_id)
        source = version.source
        original = version.original
        transformations = session.scalars(
            select(Transformation)
            .join(transformation_inputs)
            .where(transformation_inputs.c.artifact_id == original.id)
        ).all()
        return {
            "agents": [
                {
                    "id": f"publisher:{source.publisher.name}",
                    "type": "Organization",
                    "canonical_domain": source.publisher.canonical_domain,
                },
                {
                    "id": f"software:verification-core@{version.importer_version}",
                    "type": "SoftwareAgent",
                },
            ],
            "entities": [
                {
                    "id": f"artifact:{original.id}",
                    "role": "original",
                    "sha256": original.sha256,
                    "media_type": original.media_type,
                    "wasAttributedTo": f"publisher:{source.publisher.name}",
                    "retrieval": {
                        "method": version.retrieval_method,
                        "source_url": version.source_url,
                        "final_url": version.final_url,
                        "tls_host": version.tls_host,
                        "retrieved_at": iso(version.retrieved_at),
                        "http_headers": version.http_headers,
                    },
                }
            ]
            + [
                {
                    "id": f"artifact:{out.id}",
                    "role": "derived",
                    "artifact_type": out.artifact_type,
                    "sha256": out.sha256,
                    "wasGeneratedBy": f"activity:{t.id}",
                    "wasDerivedFrom": f"artifact:{original.id}",
                }
                for t in transformations
                for out in t.outputs
            ],
            "activities": [
                {
                    "id": f"activity:{t.id}",
                    "type": t.transformation_type,
                    "software": t.software_name,
                    "software_version": t.software_version,
                    "code_commit": t.code_commit,
                    "configuration_sha256": t.configuration_hash,
                    "started_at": iso(t.started_at),
                    "ended_at": iso(t.completed_at),
                    "used": [f"artifact:{a.id}" for a in t.inputs],
                    "wasAssociatedWith": f"software:{t.software_name}@{t.software_version}",
                }
                for t in transformations
            ],
        }

    @app.post(f"{API}/verify/hash", response_model=VerifyHashOut)
    def verify_hash(body: VerifyHashIn, session: SessionDep):
        digest = body.digest.lower()
        stmt = select(SourceVersion).where(SourceVersion.sha256 == digest)
        if body.source_version_id:
            stmt = stmt.where(SourceVersion.id == body.source_version_id)
        matches = [
            {
                "source_version_id": str(v.id),
                "source_id": str(v.source_id),
                "title": v.source.title,
                "retrieved_at": iso(v.retrieved_at),
                "source_url": v.source_url,
            }
            for v in session.scalars(stmt)
        ]
        return VerifyHashOut(
            match=bool(matches),
            matches=matches,
            note=(
                "A match only proves byte identity with a stored original. Compute the hash "
                "yourself and compare it with the official publisher's file as well."
            ),
        )

    @app.get(f"{API}/keys")
    def get_keys(request: Request):
        signer = request.app.state.runtime.signer
        return {
            "keys": [signer.public_key_info()] if signer else [],
            "note": (
                "Keys served here are trust-on-first-use. Pin the key id from an independent "
                "channel (repository, publication) before relying on it."
            ),
        }

    @app.get(f"{API}/audit/head", response_model=AuditHeadOut)
    def audit_head(session: SessionDep):
        ev = session.scalars(
            select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1)
        ).first()
        if ev is None:
            raise HTTPException(404, "audit log is empty")
        return AuditHeadOut(
            sequence=ev.sequence, event_hash=ev.event_hash, created_at=iso(ev.created_at)
        )

    @app.get(f"{API}/audit/events", response_model=list[AuditEventOut])
    def audit_events(
        session: SessionDep,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    ):
        events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.sequence > after)
            .order_by(AuditEvent.sequence)
            .limit(limit)
        )
        return [
            AuditEventOut(
                sequence=e.sequence,
                event_type=e.event_type,
                actor_type=e.actor_type,
                actor_id=e.actor_id,
                object_type=e.object_type,
                object_id=e.object_id,
                payload=e.event_payload,
                previous_event_hash=e.previous_event_hash,
                event_hash=e.event_hash,
                created_at=iso(e.created_at),
            )
            for e in events
        ]

    return app
