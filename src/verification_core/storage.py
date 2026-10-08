"""Write-once, content-addressed object storage.

Objects are addressed by their SHA-256, so an object can never be silently replaced:
the key changes when the content changes. A put() of an existing key is only accepted if
the bytes are identical. S3 (Infomaniak Object Storage, with Object Lock where available)
will implement the same protocol.
"""

import os
from pathlib import Path
from typing import Protocol

from .hashing import sha256_hex


class ObjectStoreError(Exception):
    pass


class ObjectStore(Protocol):
    def put(self, namespace: str, data: bytes) -> str:
        """Store bytes, return storage URI. Must be write-once."""

    def get(self, uri: str) -> bytes: ...


class LocalObjectStore:
    scheme = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ObjectStoreError(f"key escapes storage root: {key}")
        return path

    def put(self, namespace: str, data: bytes) -> str:
        if namespace not in {"originals", "derived"}:
            raise ObjectStoreError(f"unknown namespace: {namespace}")
        digest = sha256_hex(data)
        key = f"{namespace}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
        path = self._path(key)
        if path.exists():
            if sha256_hex(path.read_bytes()) != digest:
                raise ObjectStoreError(f"stored object corrupted: {key}")
            return f"{self.scheme}://{key}"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        path.chmod(0o444)
        return f"{self.scheme}://{key}"

    def get(self, uri: str) -> bytes:
        prefix = f"{self.scheme}://"
        if not uri.startswith(prefix):
            raise ObjectStoreError(f"unsupported uri: {uri}")
        key = uri[len(prefix) :]
        data = self._path(key).read_bytes()
        if sha256_hex(data) != key.rsplit("/", 1)[-1]:
            raise ObjectStoreError(f"integrity check failed for {uri}")
        return data
