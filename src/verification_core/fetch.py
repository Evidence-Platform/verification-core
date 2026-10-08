"""Retrieval of official sources with provenance metadata.

The importer fetches documents itself instead of trusting uploaded copies. It records the
requested and final URL, the TLS host, status code and the cache relevant HTTP headers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import httpx

from . import __version__
from .models import utcnow

USER_AGENT = (
    f"verification-core/{__version__} (+https://github.com/Evidence-Platform/verification-core)"
)
RECORDED_HEADERS = (
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "date",
    "server",
    "cache-control",
    "content-disposition",
)
MAX_BYTES = 200 * 1024 * 1024


class FetchError(Exception):
    pass


@dataclass
class Retrieval:
    data: bytes
    source_url: str
    final_url: str
    tls_host: str | None
    http_status: int
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=utcnow)

    @property
    def etag(self) -> str | None:
        return self.headers.get("etag")

    @property
    def last_modified(self) -> str | None:
        return self.headers.get("last-modified")


def host_matches_domain(host: str, domain: str) -> bool:
    host, domain = host.lower().rstrip("."), domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def fetch(url: str, client: httpx.Client | None = None, timeout: float = 60.0) -> Retrieval:
    if urlparse(url).scheme != "https":
        raise FetchError("only https sources are accepted")
    own_client = client is None
    client = client or httpx.Client(
        follow_redirects=True, timeout=timeout, headers={"User-Agent": USER_AGENT}
    )
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(f"request failed: {exc}") from exc
    finally:
        if own_client:
            client.close()
    if resp.status_code != 200:
        raise FetchError(f"unexpected HTTP status {resp.status_code} for {url}")
    final = str(resp.url)
    if urlparse(final).scheme != "https":
        raise FetchError(f"redirected to non-https url {final}")
    if len(resp.content) > MAX_BYTES:
        raise FetchError("document exceeds size limit")
    headers = {k: resp.headers[k] for k in RECORDED_HEADERS if k in resp.headers}
    return Retrieval(
        data=resp.content,
        source_url=url,
        final_url=final,
        tls_host=urlparse(final).hostname,
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type", "application/octet-stream"),
        headers=headers,
    )
