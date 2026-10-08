import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from conftest import make_pdf, mocked_retrieval
from verification_core.fetch import FetchError
from verification_core.hashing import canonical_json, sha256_hex
from verification_core.ingest import ingest
from verification_core.models import (
    Artifact,
    ArtifactType,
    RetrievalMethod,
    SourceVersion,
    Transformation,
)
from verification_core.signing import verify_signature


def _ingest(session, store, spec, signer, content, **kw):
    retrieval = mocked_retrieval(spec.canonical_url, content, kw.pop("final_url", None))
    return ingest(
        session,
        store,
        spec,
        retrieval,
        retrieval_method=RetrievalMethod.HTTP_FETCH,
        signer=signer,
        code_commit="test",
        **kw,
    )


def test_import_creates_immutable_chain(sessionmaker_, store, spec, signer, pdf_bytes):
    with sessionmaker_.begin() as s:
        result = _ingest(s, store, spec, signer, pdf_bytes)
        v = result.source_version
        assert result.created
        assert v.sha256 == sha256_hex(pdf_bytes)
        assert v.tls_host == "www.admin.ch"
        assert v.etag == '"abc123"'

        # original stored unchanged
        assert store.get(v.original.storage_uri) == pdf_bytes
        assert v.original.artifact_type == ArtifactType.ORIGINAL_FILE

        # derived text is a separate artifact with a transformation record
        tr = s.scalars(select(Transformation)).one()
        assert [a.id for a in tr.inputs] == [v.original.id]
        text_artifact = tr.outputs[0]
        assert text_artifact.artifact_type == ArtifactType.EXTRACTED_TEXT
        assert "Zweck des Abkommens" in store.get(text_artifact.storage_uri).decode()
        assert tr.software_name == "pypdf"

        # manifest is canonical and signed
        manifest_bytes = store.get(v.manifest.storage_uri)
        manifest = json.loads(manifest_bytes)
        assert canonical_json(manifest) == manifest_bytes
        assert manifest["original"]["sha256"] == v.sha256
        assert manifest["derived"][0]["sha256"] == text_artifact.sha256
        assert manifest["source_version"]["retrieval_method"] == "HTTP_FETCH"
        sig = json.loads(store.get(v.signature.storage_uri))
        assert verify_signature(signer.public_key, manifest_bytes, sig)


def test_reimport_same_bytes_creates_no_new_version(sessionmaker_, store, spec, signer, pdf_bytes):
    with sessionmaker_.begin() as s:
        first = _ingest(s, store, spec, signer, pdf_bytes).source_version
    with sessionmaker_.begin() as s:
        again = _ingest(s, store, spec, signer, pdf_bytes)
        assert not again.created
        assert again.source_version.id == first.id
        assert s.scalar(select(SourceVersion.id).where(SourceVersion.id != first.id)) is None


def test_changed_document_creates_linked_new_version(sessionmaker_, store, spec, signer, pdf_bytes):
    with sessionmaker_.begin() as s:
        first = _ingest(s, store, spec, signer, pdf_bytes).source_version
        first_uri = first.original.storage_uri
    changed = make_pdf("Artikel 1 Zweck des Abkommens (geändert)")
    with sessionmaker_.begin() as s:
        second = _ingest(s, store, spec, signer, changed).source_version
        assert second.previous_version_id == first.id
        assert second.version_label == "v2"
        assert second.sha256 != first.sha256
    # the first version and its original are still intact
    assert store.get(first_uri) == pdf_bytes


def test_foreign_host_is_refused(sessionmaker_, store, spec, signer, pdf_bytes):
    with sessionmaker_.begin() as s, pytest.raises(FetchError, match="does not belong"):
        _ingest(
            s,
            store,
            spec,
            signer,
            pdf_bytes,
            final_url="https://admin.ch.evil.example/abkommen.pdf",
        )


def test_redirect_within_publisher_domain_is_recorded(
    sessionmaker_, store, spec, signer, pdf_bytes
):
    with sessionmaker_.begin() as s:
        v = _ingest(
            s, store, spec, signer, pdf_bytes, final_url="https://fedlex.admin.ch/x.pdf"
        ).source_version
        assert v.final_url == "https://fedlex.admin.ch/x.pdf"
        assert v.tls_host == "fedlex.admin.ch"


def test_http_is_refused(spec):
    with pytest.raises(FetchError, match="https"):
        mocked_retrieval("http://www.admin.ch/x.pdf", b"%PDF-")


@pytest.mark.parametrize("table", ["source_versions", "artifacts", "audit_events"])
def test_evidence_tables_are_insert_only(sessionmaker_, store, spec, signer, pdf_bytes, table):
    with sessionmaker_.begin() as s:
        _ingest(s, store, spec, signer, pdf_bytes)
    with sessionmaker_() as s:
        with pytest.raises(DBAPIError, match="insert-only"):
            s.execute(text(f"UPDATE {table} SET id = id"))  # noqa: S608
        s.rollback()
        with pytest.raises(DBAPIError, match="insert-only"):
            s.execute(text(f"DELETE FROM {table}"))  # noqa: S608


def test_store_rejects_tampered_object(sessionmaker_, store, spec, signer, pdf_bytes):
    with sessionmaker_.begin() as s:
        v = _ingest(s, store, spec, signer, pdf_bytes).source_version
        uri = v.original.storage_uri
    path = store.root / uri.removeprefix("local://")
    path.chmod(0o644)
    path.write_bytes(pdf_bytes + b"x")
    with pytest.raises(Exception, match="integrity"):
        store.get(uri)


def test_artifact_hashes_match_stored_bytes(sessionmaker_, store, spec, signer, pdf_bytes):
    with sessionmaker_.begin() as s:
        _ingest(s, store, spec, signer, pdf_bytes)
        for a in s.scalars(select(Artifact)):
            data = store.get(a.storage_uri)
            assert sha256_hex(data) == a.sha256
            assert len(data) == a.byte_size
