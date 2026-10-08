# ADR-0002 Eigenes Repository für den Core, Apache-2.0

Status: angenommen, 08.10.2026

## Kontext
Der Core soll für weitere Projekte wiederverwendbar sein (Gesetzgebung, Energieprojekte, Berichte). Die erste Fachanwendung sind die Bilateralen III.

## Entscheid
- `verification-core` ist ein eigenes, öffentliches Repository unter Apache-2.0. Er enthält keine Fachlogik.
- Jede Fachanwendung (zuerst `bilaterale-iii-portal`) ist ein eigenes Repository und bindet den Core in einer fixierten Version ein. Vorschlag für Portale: AGPL-3.0, damit Betreiber eines Klons als Webdienst ihren Code offenlegen müssen.
- Der Core wird als Python-Paket und Container-Image mit Git-Tag versioniert.

## Folgen
Ein öffentlicher Core ist selbst ein Vertrauenssignal. Änderungen, die Core und Portal betreffen, brauchen zwei Pull Requests.
