# ADR-0003 Unveränderlichkeit der Belegdaten

Status: angenommen, 08.10.2026

## Kontext
Das Vertrauensmodell hängt daran, dass ein einmal veröffentlichter Beleg nicht still verändert werden kann, auch nicht durch den Betreiber.

## Entscheid
1. Objektspeicher ist inhaltsadressiert (Schlüssel = SHA-256) und write-once. Ein Objekt mit gleichem Schlüssel wird nur akzeptiert, wenn die Bytes identisch sind. Beim Lesen wird der Hash erneut geprüft.
2. Die Tabellen `artifacts`, `source_versions`, `transformations`, `transformation_inputs`, `transformation_outputs`, `audit_events` sind insert-only. Die Anwendung kennt keine Update- und Löschpfade. Unter PostgreSQL verhindern Trigger UPDATE, DELETE und TRUNCATE.
3. «Aktuelle Version» ist kein Flag, sondern die jüngste Version einer Quelle. Damit muss keine bestehende Zeile geändert werden.
4. In Produktion zusätzlich Object Lock (WORM) im S3-Speicher, sofern Infomaniak dies anbietet.

## Folgen
Ein Datenbankadministrator kann die Trigger entfernen. Das verhindert die Trigger nicht, es macht aber jede Manipulation absichtlich. Dagegen helfen das hashverkettete Audit-Log und das externe Verankern des Audit-Heads (ADR-0005). Rechtlich notwendige Löschungen (z. B. Personendaten) sind im Core nicht vorgesehen, weil er nur öffentliche Dokumente speichert.
