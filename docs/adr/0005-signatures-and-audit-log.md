# ADR-0005 Ed25519-Signaturen und hashverkettetes Audit-Log

Status: angenommen, 08.10.2026

## Entscheid
- Jedes Quellmanifest wird über seine RFC-8785-Bytes mit Ed25519 signiert. Key-ID = SHA-256 des rohen öffentlichen Schlüssels.
- Entwicklung und Beta: Schlüssel als PEM-Datei ausserhalb des Repositories. Produktion: Schlüssel in KMS/HSM, der Anwendungsprozess erhält nur eine Signierfunktion.
- Die Key-ID des Produktionsschlüssels wird im Repository und auf der Website veröffentlicht, damit Prüfer ihn unabhängig fixieren können.
- Jede Änderung erzeugt ein Audit-Ereignis, dessen Hash den Vorgänger einschliesst. Der aktuelle Head ist öffentlich (`/api/v1/audit/head`), alle Ereignisse ebenfalls (`/api/v1/audit/events`).

## Später
RFC-3161-Zeitstempel für Manifeste und periodisches Verankern des Audit-Heads in einem Transparency Log (z. B. Rekor). Eine Blockchain nur, wenn sie gegenüber diesen Mitteln einen belegbaren Mehrwert bringt.
