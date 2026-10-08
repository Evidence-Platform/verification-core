import io
import os
from pathlib import Path

import httpx
import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, text

from verification_core.db import make_engine, make_sessionmaker, upgrade_database
from verification_core.fetch import Retrieval, fetch
from verification_core.ingest import SourceSpec
from verification_core.settings_runtime import Runtime
from verification_core.signing import Signer, generate_private_key_pem
from verification_core.storage import LocalObjectStore


def make_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setTitle("test")
    c.drawString(72, 720, text)
    c.save()
    return buf.getvalue()


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf("Artikel 1 Zweck des Abkommens")


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """SQLite by default. Set VCORE_TEST_DATABASE_URL to run the suite against PostgreSQL
    (the database is wiped before every test)."""
    url = os.environ.get("VCORE_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    if url.startswith("postgresql"):
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        engine.dispose()
    upgrade_database(url)  # real migrations, including immutability triggers
    return url


@pytest.fixture
def sessionmaker_(db_url):
    return make_sessionmaker(make_engine(db_url))


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


@pytest.fixture
def signer(tmp_path: Path) -> Signer:
    key = tmp_path / "key.pem"
    key.write_bytes(generate_private_key_pem())
    return Signer.from_pem_file(key, "test-operator")


@pytest.fixture
def runtime(sessionmaker_, store, signer) -> Runtime:
    return Runtime(sessionmaker=sessionmaker_, store=store, signer=signer)


@pytest.fixture
def spec() -> SourceSpec:
    return SourceSpec(
        project_slug="demo",
        project_name="Demo",
        publisher_name="Bundesrat",
        publisher_domain="admin.ch",
        publisher_type="GOVERNMENT",
        publisher_country="CH",
        source_type="TREATY",
        title="Testabkommen",
        canonical_url="https://www.admin.ch/docs/abkommen.pdf",
        language="de",
    )


def mocked_retrieval(url: str, content: bytes, final_url: str | None = None) -> Retrieval:
    """Run the real fetch() against an in-memory transport."""

    def handler(request: httpx.Request) -> httpx.Response:
        if final_url and str(request.url) == url:
            return httpx.Response(302, headers={"location": final_url})
        return httpx.Response(
            200,
            content=content,
            headers={
                "content-type": "application/pdf",
                "etag": '"abc123"',
                "last-modified": "Tue, 06 Oct 2026 08:00:00 GMT",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return fetch(url, client=client)
