"""Text extraction from original files. Output is always a derived artifact, never 'the original'.

Every extractor declares its name, version and configuration. These end up in the
transformation record, so the derived text can be reproduced and re-checked independently.
"""

import io
from dataclasses import dataclass, field

import pypdf

from .hashing import canonical_sha256


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    media_type: str
    software_name: str
    software_version: str
    configuration: dict = field(default_factory=dict)

    @property
    def configuration_hash(self) -> str:
        return canonical_sha256(self.configuration)


PDF_CONFIG = {"extractor": "pypdf.PdfReader.extract_text", "page_separator": "\f"}


def extract_pdf_text(data: bytes) -> ExtractionResult:
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return ExtractionResult(
        text=PDF_CONFIG["page_separator"].join(pages),
        media_type="text/plain; charset=utf-8",
        software_name="pypdf",
        software_version=pypdf.__version__,
        configuration=PDF_CONFIG,
    )


def extract(data: bytes, content_type: str) -> ExtractionResult | None:
    """Return extracted text, or None if no extractor exists for this media type yet."""
    base = content_type.split(";")[0].strip().lower()
    if base == "application/pdf" or data[:5] == b"%PDF-":
        return extract_pdf_text(data)
    return None
