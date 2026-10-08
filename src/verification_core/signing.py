"""Ed25519 signatures over canonical JSON (RFC 8785).

The signature covers the exact canonical bytes of a document. Anyone holding the public key
can verify it with any Ed25519 implementation; nothing platform specific is required.

Production: the private key belongs in a KMS/HSM, not on the application server (ADR-0005).
The file based signer below is for development and the first beta.
"""

import base64
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .hashing import sha256_hex

ALGORITHM = "Ed25519"


def _raw_public(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id(key: Ed25519PublicKey) -> str:
    """Key id = SHA-256 of the raw 32-byte public key, hex encoded."""
    return sha256_hex(_raw_public(key))


@dataclass(frozen=True)
class Signer:
    private_key: Ed25519PrivateKey
    signer_name: str

    @classmethod
    def from_pem_file(cls, path: Path, signer_name: str) -> "Signer":
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("signing key must be an Ed25519 private key")
        return cls(key, signer_name)

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self.private_key.public_key()

    @property
    def key_id(self) -> str:
        return key_id(self.public_key)

    def sign(self, payload: bytes) -> dict:
        return {
            "alg": ALGORITHM,
            "keyid": self.key_id,
            "signer": self.signer_name,
            "payload_sha256": sha256_hex(payload),
            "sig": base64.b64encode(self.private_key.sign(payload)).decode("ascii"),
        }

    def public_key_info(self) -> dict:
        return public_key_info(self.public_key, self.signer_name)


def public_key_info(key: Ed25519PublicKey, signer_name: str) -> dict:
    pem = key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    return {
        "alg": ALGORITHM,
        "keyid": key_id(key),
        "signer": signer_name,
        "public_key_raw_b64": base64.b64encode(_raw_public(key)).decode("ascii"),
        "public_key_pem": pem,
    }


def load_public_key(raw_b64: str | None = None, pem: str | None = None) -> Ed25519PublicKey:
    if raw_b64:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw_b64))
    if pem:
        key = serialization.load_pem_public_key(pem.encode("ascii"))
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("not an Ed25519 public key")
        return key
    raise ValueError("no public key given")


def verify_signature(public_key: Ed25519PublicKey, payload: bytes, signature: dict) -> bool:
    if signature.get("alg") != ALGORITHM:
        return False
    if signature.get("keyid") != key_id(public_key):
        return False
    try:
        public_key.verify(base64.b64decode(signature["sig"]), payload)
    except (InvalidSignature, KeyError, ValueError):
        return False
    return True


def generate_private_key_pem() -> bytes:
    return Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
