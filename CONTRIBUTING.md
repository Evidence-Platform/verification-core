# Mitwirken

Beiträge sind willkommen. Bitte zuerst [CLAUDE.md](CLAUDE.md) lesen, dort stehen die harten Regeln, die für Menschen und KI-Agenten gleich gelten.

## Ablauf
1. Issue eröffnen oder bestehendes Issue kommentieren.
2. Branch von `main`, ein Pull Request pro Story.
3. `ruff check . && ruff format --check . && pytest` muss lokal grün sein, idealerweise auch mit `VCORE_TEST_DATABASE_URL` gegen PostgreSQL.
4. Architekturentscheide als ADR unter `docs/adr/`.
5. Jeder Pull Request braucht ein Review. Änderungen an Hashing, Signaturen, Migrationen oder Unveränderlichkeit brauchen zwei.

## Lizenz
Mit einem Beitrag stimmst du zu, dass er unter Apache-2.0 veröffentlicht wird.
