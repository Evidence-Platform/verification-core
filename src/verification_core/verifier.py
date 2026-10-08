"""Independent verifier for a platform running verification-core.

Uses only the public API and standard cryptography. It deliberately does not trust the
platform's own verdicts: every hash is recomputed locally, and the original can be compared
with the publisher's file fetched directly from the official URL.
"""

from dataclasses import dataclass, field
from enum import StrEnum

import httpx

from .hashing import canonical_json, sha256_hex
from .signing import load_public_key, verify_signature


class Status(StrEnum):
    PASS = "PASS"  # noqa: S105 - status label, not a secret
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class Check:
    name: str
    status: Status
    detail: str


@dataclass
class Report:
    source_version_id: str
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != Status.FAIL for c in self.checks)

    def add(self, name: str, status: Status, detail: str) -> None:
        self.checks.append(Check(name, status, detail))


def verify_source_version(
    api_base: str,
    source_version_id: str,
    *,
    pinned_public_key_b64: str | None = None,
    compare_official: bool = False,
    client: httpx.Client | None = None,
) -> Report:
    own = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    base = api_base.rstrip("/") + "/api/v1"
    report = Report(source_version_id)
    try:
        version = (
            client.get(f"{base}/source-versions/{source_version_id}").raise_for_status().json()
        )
        envelope = (
            client.get(f"{base}/source-versions/{source_version_id}/manifest")
            .raise_for_status()
            .json()
        )
        original = (
            client.get(f"{base}/source-versions/{source_version_id}/original")
            .raise_for_status()
            .content
        )

        manifest = envelope["manifest"]
        manifest_bytes = canonical_json(manifest)
        manifest_digest = sha256_hex(manifest_bytes)
        original_digest = sha256_hex(original)

        # 1. Original bytes match the manifest.
        declared = manifest["original"]["sha256"]
        report.add(
            "original_hash",
            Status.PASS if original_digest == declared == version["sha256"] else Status.FAIL,
            f"computed {original_digest}, manifest {declared}, api {version['sha256']}",
        )
        report.add(
            "original_size",
            Status.PASS if len(original) == manifest["original"]["byte_size"] else Status.FAIL,
            f"{len(original)} bytes",
        )

        # 2. Manifest canonicalisation is reproducible.
        report.add(
            "manifest_hash",
            Status.PASS
            if manifest_digest == envelope["manifest_sha256"] == version["manifest_sha256"]
            else Status.FAIL,
            f"computed {manifest_digest} (RFC 8785)",
        )
        report.add(
            "manifest_subject",
            Status.PASS if manifest["source_version"]["id"] == source_version_id else Status.FAIL,
            "manifest refers to the requested source version",
        )

        # 3. Signature.
        signatures = envelope.get("signatures", [])
        if not signatures:
            report.add("signature", Status.WARN, "manifest is not signed")
        else:
            if pinned_public_key_b64:
                key = load_public_key(raw_b64=pinned_public_key_b64)
                origin = "pinned key"
            else:
                keys = client.get(f"{base}/keys").raise_for_status().json()["keys"]
                by_id = {k["keyid"]: k for k in keys}
                info = by_id.get(signatures[0]["keyid"])
                key = load_public_key(raw_b64=info["public_key_raw_b64"]) if info else None
                origin = "key served by the platform (trust on first use)"
            valid = key is not None and any(
                verify_signature(key, manifest_bytes, s) for s in signatures
            )
            status = Status.PASS if valid else Status.FAIL
            if valid and not pinned_public_key_b64:
                status = Status.WARN
            report.add("signature", status, f"Ed25519, {origin}")

        # 4. Provenance quality.
        method = manifest["source_version"]["retrieval_method"]
        report.add(
            "retrieval_method",
            Status.PASS if method == "HTTP_FETCH" else Status.WARN,
            "fetched from official URL by the importer"
            if method == "HTTP_FETCH"
            else "manually uploaded copy; origin not proven by retrieval",
        )

        # 5. Independent comparison with the publisher's current file.
        if compare_official:
            url = (
                manifest["source_version"]["final_url"] or manifest["source_version"]["source_url"]
            )
            try:
                official = client.get(url).raise_for_status().content
                official_digest = sha256_hex(official)
                if official_digest == original_digest:
                    report.add("official_comparison", Status.PASS, f"identical to {url}")
                else:
                    report.add(
                        "official_comparison",
                        Status.WARN,
                        f"publisher now serves different bytes ({official_digest}); the "
                        f"document may have been updated after "
                        f"{manifest['source_version']['retrieved_at']}",
                    )
            except httpx.HTTPError as exc:
                report.add("official_comparison", Status.WARN, f"could not fetch {url}: {exc}")
        else:
            report.add("official_comparison", Status.SKIP, "use --compare-official")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        report.add("retrieval", Status.FAIL, f"could not complete verification: {exc}")
    finally:
        if own:
            client.close()
    return report
