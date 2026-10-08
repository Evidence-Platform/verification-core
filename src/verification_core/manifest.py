"""Source manifests: the machine-readable, signable statement about one source version.

A manifest binds together: which publisher, which URL, when retrieved, how retrieved, the
SHA-256 of the unchanged original and of every derived artifact with the software that
produced it. It is serialised with RFC 8785 so that its hash and signature are reproducible.
"""

from typing import Any

from .db import iso
from .models import Artifact, Project, Publisher, Source, SourceVersion, Transformation

SOURCE_MANIFEST_SCHEMA = (
    "https://github.com/Evidence-Platform/verification-core/blob/main/schemas/"
    "source-manifest.v1.schema.json"
)


def build_source_manifest(
    *,
    project: Project,
    publisher: Publisher,
    source: Source,
    version: SourceVersion,
    original: Artifact,
    derived: list[tuple[Artifact, Transformation]],
    importer: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "manifest_type": "source_version",
        "project": project.slug,
        "publisher": {
            "name": publisher.name,
            "canonical_domain": publisher.canonical_domain,
        },
        "source": {
            "id": str(source.id),
            "title": source.title,
            "source_type": source.source_type,
            "canonical_url": source.canonical_url,
            "language": source.language,
            "external_identifier": source.external_identifier,
        },
        "source_version": {
            "id": str(version.id),
            "version_label": version.version_label,
            "previous_version_id": (
                str(version.previous_version_id) if version.previous_version_id else None
            ),
            "retrieval_method": version.retrieval_method,
            "retrieved_at": iso(version.retrieved_at),
            "source_url": version.source_url,
            "final_url": version.final_url,
            "tls_host": version.tls_host,
            "http_status": version.http_status,
            "etag": version.etag,
            "last_modified": version.last_modified,
        },
        "original": {
            "artifact_id": str(original.id),
            "media_type": original.media_type,
            "byte_size": original.byte_size,
            "sha256": original.sha256,
        },
        "derived": [
            {
                "artifact_id": str(art.id),
                "artifact_type": art.artifact_type,
                "media_type": art.media_type,
                "byte_size": art.byte_size,
                "sha256": art.sha256,
                "transformation": {
                    "id": str(tr.id),
                    "type": tr.transformation_type,
                    "software": tr.software_name,
                    "software_version": tr.software_version,
                    "code_commit": tr.code_commit,
                    "configuration_sha256": tr.configuration_hash,
                },
            }
            for art, tr in derived
        ],
        "importer": importer,
    }
