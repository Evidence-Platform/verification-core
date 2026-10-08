"""Command line interface: `vcore --help`."""

import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from . import audit
from .config import get_settings
from .db import session_scope, upgrade_database
from .fetch import FetchError, Retrieval, fetch
from .ingest import IngestError, SourceSpec, ingest
from .models import RetrievalMethod, utcnow
from .settings_runtime import build_runtime
from .signing import generate_private_key_pem
from .verifier import Status, verify_source_version

app = typer.Typer(help="verification-core: verifiable sources, manifests and provenance.")


@app.command("init-db")
def init_db() -> None:
    """Apply database migrations."""
    upgrade_database(get_settings().database_url)
    typer.echo("database is up to date")


@app.command()
def keygen(
    out: Annotated[Path, typer.Option(help="Where to write the Ed25519 private key (PEM).")],
) -> None:
    """Generate an Ed25519 signing key for development. Use a KMS in production."""
    if out.exists():
        raise typer.BadParameter(f"{out} exists, refusing to overwrite")
    out.write_bytes(generate_private_key_pem())
    out.chmod(0o600)
    typer.echo(f"written {out}; set VCORE_SIGNING_KEY_PATH={out}")


@app.command("import")
def import_source(
    project: Annotated[str, typer.Option(help="Project slug, e.g. bilaterale-iii")],
    publisher: Annotated[str, typer.Option(help="Publisher name, e.g. 'Bundesrat'")],
    title: Annotated[str, typer.Option()],
    url: Annotated[str, typer.Option(help="Official URL of the document (https)")],
    source_type: Annotated[str, typer.Option()] = "DOCUMENT",
    publisher_domain: Annotated[str | None, typer.Option(help="e.g. admin.ch")] = None,
    publisher_type: Annotated[str | None, typer.Option()] = None,
    country: Annotated[str | None, typer.Option()] = None,
    language: Annotated[str | None, typer.Option()] = None,
    external_id: Annotated[str | None, typer.Option()] = None,
    project_name: Annotated[str | None, typer.Option()] = None,
    file: Annotated[
        Path | None,
        typer.Option(help="Import a local copy instead of fetching. Marked MANUAL_UPLOAD."),
    ] = None,
    retrieved_at: Annotated[
        datetime | None, typer.Option(help="For --file: when the copy was downloaded (UTC)")
    ] = None,
) -> None:
    """Fetch (or load) a document, store it immutably and create a signed manifest."""
    settings = get_settings()
    runtime = build_runtime(settings)
    spec = SourceSpec(
        project_slug=project,
        project_name=project_name,
        publisher_name=publisher,
        publisher_domain=publisher_domain,
        publisher_type=publisher_type,
        publisher_country=country,
        source_type=source_type,
        title=title,
        canonical_url=url,
        language=language,
        external_identifier=external_id,
    )
    try:
        if file is None:
            retrieval = fetch(url)
            method = RetrievalMethod.HTTP_FETCH
        else:
            content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            retrieval = Retrieval(
                data=file.read_bytes(),
                source_url=url,
                final_url=None,
                tls_host=None,
                http_status=None,
                content_type=content_type,
                retrieved_at=retrieved_at or utcnow(),
            )
            method = RetrievalMethod.MANUAL_UPLOAD
        with session_scope(runtime.sessionmaker) as session:
            result = ingest(
                session,
                runtime.store,
                spec,
                retrieval,
                retrieval_method=method,
                signer=runtime.signer,
                code_commit=settings.code_commit,
                enforce_publisher_domain=settings.enforce_publisher_domain,
            )
            v = result.source_version
            typer.echo(
                json.dumps(
                    {
                        "created": result.created,
                        "source_version_id": str(v.id),
                        "source_id": str(v.source_id),
                        "version_label": v.version_label,
                        "sha256": v.sha256,
                        "retrieval_method": v.retrieval_method,
                        "signed": v.signature_artifact_id is not None,
                    },
                    indent=2,
                )
            )
    except (FetchError, IngestError) as exc:
        typer.echo(f"import refused: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def verify(
    api: Annotated[str, typer.Option(help="Base URL of the platform, e.g. https://example.ch")],
    source_version: Annotated[str, typer.Option(help="Source version id")],
    pubkey: Annotated[
        str | None, typer.Option(help="Pinned Ed25519 public key (raw, base64)")
    ] = None,
    compare_official: Annotated[
        bool, typer.Option(help="Also fetch the publisher's file and compare hashes")
    ] = False,
) -> None:
    """Verify a source version independently, using only the public API."""
    report = verify_source_version(
        api, source_version, pinned_public_key_b64=pubkey, compare_official=compare_official
    )
    for c in report.checks:
        typer.echo(f"[{c.status.value:4}] {c.name}: {c.detail}")
    typer.echo("RESULT: " + ("no failures" if report.ok else "FAILED"))
    if not report.ok:
        raise typer.Exit(1)
    if any(c.status == Status.WARN for c in report.checks):
        typer.echo("note: warnings need human judgement, see detail lines")


@app.command("audit-verify")
def audit_verify() -> None:
    """Recompute the local audit hash chain."""
    runtime = build_runtime()
    with session_scope(runtime.sessionmaker) as session:
        ok, findings = audit.verify_chain(session)
        head = audit.head(session)
    for f in findings:
        typer.echo(f"finding: {f}")
    if head:
        typer.echo(f"head: sequence {head.sequence}, hash {head.event_hash}")
    typer.echo("RESULT: " + ("chain intact" if ok else "CHAIN BROKEN"))
    if not ok:
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the public API (development server)."""
    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    app()
