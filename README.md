# verification-core

**Don't trust us. Verify us.**

Generischer Kern für Informationsplattformen, die sich von aussen überprüfen lassen. Der Core verwaltet Quellen, unveränderliche Originaldateien, SHA-256-Hashes, Herkunftsdaten, abgeleitete Artefakte und signierte Manifeste. Er enthält keine Fachlogik eines bestimmten Projekts. Die erste Anwendung ist eine neutrale Informationsplattform zu den Bilateralen III (separates Repository).

*English summary.* A domain-neutral core for information platforms that third parties can verify independently. It stores official source documents immutably, hashes them, records how and when they were retrieved, derives text with recorded transformations, and publishes RFC 8785 canonical manifests signed with Ed25519. A public read API and an independent verifier CLI let anyone recompute every hash and check every signature.

## Was der Core heute kann (Version 0.1)

Die erste vertikale Story aus der technischen Spezifikation (Kap. 37) ist umgesetzt:

1. Ein offizielles Dokument wird direkt von der Quell-URL abgerufen (nur HTTPS, nur von der Domain des registrierten Herausgebers).
2. Das Original wird unverändert, inhaltsadressiert und schreibgeschützt gespeichert.
3. SHA-256, Abrufzeit, finale URL, TLS-Host, Statuscode und relevante HTTP-Header werden festgehalten.
4. Der Text wird als **abgeleitetes** Artefakt extrahiert. Software, Version, Code-Commit und Konfigurationshash stehen im Transformationsdatensatz.
5. Ein Manifest bindet alles zusammen, wird nach RFC 8785 kanonisiert und mit Ed25519 signiert.
6. Jede Änderung landet in einem hashverketteten Audit-Log.
7. Die öffentliche API liefert Original, Manifest, Signatur, Schlüssel, Provenienz und Audit-Kette.
8. `vcore verify` prüft eine Quellversion unabhängig, nur über die öffentliche API, und kann das Original mit der aktuellen Datei des Herausgebers vergleichen.

Unveränderlichkeit ist doppelt abgesichert. Die Anwendung kennt keine Update- oder Löschpfade für Artefakte, Quellversionen, Transformationen und Audit-Ereignisse, und unter PostgreSQL verhindern Trigger UPDATE und DELETE auf diesen Tabellen.

## Schnellstart

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,postgres]"

vcore keygen --out dev-signing-key.pem
export VCORE_SIGNING_KEY_PATH=dev-signing-key.pem
export VCORE_SIGNER_NAME="local-dev"
vcore init-db

vcore import \
  --project demo --publisher "Beispiel-Herausgeber" --publisher-domain example.org \
  --title "Beispieldokument" --url https://example.org/dokument.pdf

vcore serve            # API auf http://127.0.0.1:8000, Doku unter /docs
vcore verify --api http://127.0.0.1:8000 --source-version <id> --compare-official
```

Mit PostgreSQL: `docker compose up -d db` und `VCORE_DATABASE_URL=postgresql+psycopg://vcore:vcore@localhost:5432/vcore`.

## Selbst prüfen, ohne unsere Software

Die Prüfung braucht keinen Code aus diesem Repository:

```bash
curl -s $API/api/v1/source-versions/$ID/original -o original.bin
sha256sum original.bin                 # muss manifest.original.sha256 entsprechen
curl -s $API/api/v1/source-versions/$ID/manifest > m.json
curl -s $API/api/v1/keys > k.json

# Manifest kanonisieren (RFC 8785; für diese Manifeste ohne Fliesskommazahlen genügt die Standardbibliothek)
python3 -c "import json;m=json.load(open('m.json'));open('payload.bin','wb').write(json.dumps(m['manifest'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())"
sha256sum payload.bin                  # muss manifest_sha256 entsprechen

# Signatur mit OpenSSL prüfen
python3 -c "import json,base64;m=json.load(open('m.json'));open('sig.bin','wb').write(base64.b64decode(m['signatures'][0]['sig']));open('pub.pem','w').write(json.load(open('k.json'))['keys'][0]['public_key_pem'])"
openssl pkeyutl -verify -pubin -inkey pub.pem -rawin -in payload.bin -sigfile sig.bin
```

Den öffentlichen Schlüssel bitte über einen unabhängigen Kanal festhalten (Key-ID im Repository bzw. in der Veröffentlichung des Betreibers) und nicht nur über `/api/v1/keys` beziehen. Sonst prüft man den Betreiber mit einem Schlüssel, den der Betreiber selbst liefert.

## Was ein Hash beweist und was nicht

| Frage | Nachweis |
|---|---|
| Ist die Datei unverändert? | SHA-256 |
| Woher stammt sie? | Abruf von der offiziellen URL, TLS-Host, Herausgeber-Domain, signiertes Manifest |
| Wann lag diese Version vor? | Abrufzeit im Manifest; später RFC-3161-Zeitstempel und Transparency Log |
| Woraus folgt eine Aussage? | Claim/Evidence-Modell (nächste Ausbaustufe) |
| Kann ein Dritter das nachprüfen? | Öffentliche API, Originale, kanonische Manifeste, `vcore verify` |

Ein Hash sagt nichts darüber, ob ein Herausgeber vertrauenswürdig ist oder ob ein Dokument rechtlich die gültige Fassung ist.

## Aufbau

```
src/verification_core/
  models.py       Datenmodell (Projekt, Herausgeber, Quelle, Quellversion, Artefakt, Transformation, Audit)
  fetch.py        Abruf mit Herkunftsdaten
  storage.py      Write-once, inhaltsadressierter Objektspeicher
  extraction.py   Textextraktion als abgeleitetes Artefakt
  manifest.py     Quellmanifest
  signing.py      Ed25519 über RFC-8785-Bytes
  audit.py        Hashverkettetes Audit-Log
  ingest.py       Importpipeline
  api/            Öffentliche Read-API (FastAPI, OpenAPI unter /docs)
  verifier.py     Unabhängiger Prüfer
  migrations/     Alembic, inkl. Unveränderlichkeits-Trigger für PostgreSQL
docs/adr/         Architekturentscheide
schemas/          JSON Schema des Quellmanifests
```

## Roadmap des Core

- [x] Quellen, Versionen, Artefakte, SHA-256, Provenienz, Manifest, Signatur, Audit-Kette, Read-API, Verifier
- [ ] S3-Objektspeicher (Infomaniak) mit Object Lock
- [ ] Dokumentstruktur (`document_nodes`) mit stabilen Lokatoren, Chunks, Embeddings
- [ ] Claim/Evidence-Modell und Verification Bundle
- [ ] MCP-Server (read-only)
- [ ] RFC-3161-Zeitstempel, Transparency Log
- [ ] Rollen und Vier-Augen-Freigabe für Quellen
- [ ] Sprachfassungen: amtliche Fassungen eines Dokuments (de, fr, it, rm) als verknüpfte Quellen; Übersetzungen der Plattform als eigene, gekennzeichnete Ableitungen

## Lizenz

Apache-2.0, siehe [LICENSE](LICENSE).
