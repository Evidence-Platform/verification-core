"""Wires settings into live objects (engine, storage, signer) for the API and the CLI."""

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker
from .signing import Signer
from .storage import LocalObjectStore, ObjectStore


@dataclass
class Runtime:
    sessionmaker: sessionmaker[Session]
    store: ObjectStore
    signer: Signer | None
    settings: Settings | None = None


def build_runtime(settings: Settings | None = None) -> Runtime:
    settings = settings or get_settings()
    signer = (
        Signer.from_pem_file(settings.signing_key_path, settings.signer_name)
        if settings.signing_key_path
        else None
    )
    return Runtime(
        sessionmaker=make_sessionmaker(make_engine(settings.database_url)),
        store=LocalObjectStore(settings.storage_path),
        signer=signer,
        settings=settings,
    )
