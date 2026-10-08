# ADR-0004 UUIDv7 und RFC 8785

Status: angenommen, 08.10.2026

## Entscheid
- Alle Primärschlüssel sind UUIDv7 (zeitlich sortierbar, ohne zentrale Vergabe).
- Jedes gehashte oder signierte JSON-Dokument wird nach RFC 8785 (JSON Canonicalization Scheme) serialisiert.
- Zeitpunkte in gehashten Dokumenten immer als UTC im Format `YYYY-MM-DDTHH:MM:SS.ffffffZ` (`db.iso()`).

## Begründung
Ein Dritter muss Hash und Signatur mit einer beliebigen Implementierung reproduzieren können, ohne unseren Code. RFC 8785 ist dafür der Standard.
