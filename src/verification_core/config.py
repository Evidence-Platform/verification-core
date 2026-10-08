"""Runtime configuration, read from environment variables prefixed with VCORE_."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VCORE_", env_file=".env", extra="ignore")

    # SQLAlchemy URL. PostgreSQL in production, SQLite is fine for local experiments and tests.
    database_url: str = "sqlite:///./vcore.db"

    # Root directory of the local write-once object store.
    storage_path: Path = Path("./data/objects")

    # Ed25519 private key (PEM). If unset, manifests are produced unsigned.
    signing_key_path: Path | None = None

    # Human readable identifier of the operator that signs manifests.
    signer_name: str = "unconfigured-operator"

    # Git commit of the running code, injected at build time. Recorded in every transformation.
    code_commit: str = "unknown"

    # Refuse to import from hosts that do not belong to the publisher's canonical domain.
    enforce_publisher_domain: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
