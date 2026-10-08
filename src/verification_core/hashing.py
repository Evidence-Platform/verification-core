"""Hashing and canonical JSON.

SHA-256 over raw bytes answers exactly one question: are two byte sequences identical?
It says nothing about origin or legal validity. Origin is covered by provenance metadata
and manifest signatures.
"""

import hashlib
from typing import Any

import rfc8785


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    """Serialise according to RFC 8785 (JSON Canonicalization Scheme).

    Identical logical content always yields identical bytes, so hashes and signatures over
    JSON documents are reproducible by any independent implementation of RFC 8785.
    """
    return rfc8785.dumps(obj)


def canonical_sha256(obj: Any) -> str:
    return sha256_hex(canonical_json(obj))
