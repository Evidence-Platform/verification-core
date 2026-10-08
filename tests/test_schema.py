import json
from pathlib import Path

import jsonschema

from conftest import mocked_retrieval
from verification_core.ingest import ingest
from verification_core.manifest import SOURCE_MANIFEST_SCHEMA
from verification_core.models import RetrievalMethod

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "schemas" / "source-manifest.v1.schema.json").read_text()
)


def test_manifest_matches_published_schema(sessionmaker_, store, spec, signer, pdf_bytes):
    assert SCHEMA["$id"] == SOURCE_MANIFEST_SCHEMA
    with sessionmaker_.begin() as s:
        v = ingest(
            s,
            store,
            spec,
            mocked_retrieval(spec.canonical_url, pdf_bytes),
            retrieval_method=RetrievalMethod.HTTP_FETCH,
            signer=signer,
        ).source_version
        manifest = json.loads(store.get(v.manifest.storage_uri))
    jsonschema.validate(manifest, SCHEMA, format_checker=jsonschema.FormatChecker())
