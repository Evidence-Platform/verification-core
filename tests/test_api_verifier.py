import base64

import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from conftest import mocked_retrieval
from verification_core.api import create_app
from verification_core.hashing import canonical_json, sha256_hex
from verification_core.ingest import ingest
from verification_core.models import RetrievalMethod
from verification_core.verifier import Status, verify_source_version


@pytest.fixture
def imported(runtime, spec, pdf_bytes):
    with runtime.sessionmaker.begin() as s:
        v = ingest(
            s,
            runtime.store,
            spec,
            mocked_retrieval(spec.canonical_url, pdf_bytes),
            retrieval_method=RetrievalMethod.HTTP_FETCH,
            signer=runtime.signer,
        ).source_version
        return str(v.id), str(v.source_id)


@pytest.fixture
def client(runtime):
    return TestClient(create_app(runtime), base_url="http://testserver")


def _pinned(runtime) -> str:
    raw = runtime.signer.public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode()


def test_public_endpoints(client, imported, pdf_bytes):
    version_id, source_id = imported
    projects = client.get("/api/v1/projects").json()
    assert projects[0]["slug"] == "demo"

    sources = client.get("/api/v1/projects/demo/sources").json()
    assert sources[0]["current_version_id"] == version_id
    assert sources[0]["publisher"]["canonical_domain"] == "admin.ch"

    versions = client.get(f"/api/v1/sources/{source_id}/versions").json()
    assert [v["id"] for v in versions] == [version_id]

    original = client.get(f"/api/v1/source-versions/{version_id}/original")
    assert original.content == pdf_bytes
    assert original.headers["x-content-sha256"] == sha256_hex(pdf_bytes)

    envelope = client.get(f"/api/v1/source-versions/{version_id}/manifest").json()
    assert sha256_hex(canonical_json(envelope["manifest"])) == envelope["manifest_sha256"]

    prov = client.get(f"/api/v1/source-versions/{version_id}/provenance").json()
    assert prov["activities"][0]["type"] == "TEXT_EXTRACTION"
    assert prov["entities"][0]["retrieval"]["tls_host"] == "www.admin.ch"

    hit = client.post("/api/v1/verify/hash", json={"digest": sha256_hex(pdf_bytes)}).json()
    assert hit["match"] and hit["matches"][0]["source_version_id"] == version_id
    miss = client.post("/api/v1/verify/hash", json={"digest": "0" * 64}).json()
    assert not miss["match"]

    head = client.get("/api/v1/audit/head").json()
    events = client.get("/api/v1/audit/events").json()
    assert events[-1]["event_hash"] == head["event_hash"]

    assert client.get("/openapi.json").status_code == 200


def test_verifier_passes_with_pinned_key(client, imported, runtime):
    version_id, _ = imported
    report = verify_source_version(
        "http://testserver", version_id, pinned_public_key_b64=_pinned(runtime), client=client
    )
    status = {c.name: c.status for c in report.checks}
    assert report.ok, report.checks
    assert status["original_hash"] == Status.PASS
    assert status["manifest_hash"] == Status.PASS
    assert status["signature"] == Status.PASS
    assert status["retrieval_method"] == Status.PASS


def test_verifier_warns_on_trust_on_first_use_key(client, imported):
    version_id, _ = imported
    report = verify_source_version("http://testserver", version_id, client=client)
    assert {c.name: c.status for c in report.checks}["signature"] == Status.WARN


def test_verifier_rejects_wrong_pinned_key(client, imported, tmp_path):
    from verification_core.signing import Signer, generate_private_key_pem

    other = tmp_path / "other.pem"
    other.write_bytes(generate_private_key_pem())
    raw = Signer.from_pem_file(other, "x").public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    version_id, _ = imported
    report = verify_source_version(
        "http://testserver",
        version_id,
        pinned_public_key_b64=base64.b64encode(raw).decode(),
        client=client,
    )
    assert not report.ok


def test_verifier_detects_tampered_original(client, imported, runtime, pdf_bytes):
    version_id, _ = imported
    for path in runtime.store.root.rglob("*"):
        if path.is_file() and path.read_bytes() == pdf_bytes:
            path.chmod(0o644)
            path.write_bytes(pdf_bytes + b"%tampered\n")
    tolerant = TestClient(client.app, base_url="http://testserver", raise_server_exceptions=False)
    report = verify_source_version(
        "http://testserver", version_id, pinned_public_key_b64=_pinned(runtime), client=tolerant
    )
    assert not report.ok


def test_unknown_ids_return_404(client):
    assert (
        client.get("/api/v1/source-versions/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )
    assert client.get("/api/v1/projects/nope/sources").status_code == 404
