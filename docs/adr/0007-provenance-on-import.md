# ADR-0007 Herkunftsprüfung beim Import

Status: angenommen, 08.10.2026

## Entscheid
- Der Importer ruft Dokumente selbst von der offiziellen URL ab (nur HTTPS) und speichert finale URL, TLS-Host, Statuscode und relevante Header.
- Jeder Herausgeber hat eine kanonische Domain. Liegt der finale Host nicht in dieser Domain, wird der Import abgelehnt (Schutz gegen Weiterleitungen und untergeschobene Dateien).
- Manuell hochgeladene Kopien sind möglich, werden aber als `MANUAL_UPLOAD` gekennzeichnet. Der Verifier meldet sie als Warnung.
- Ein erneuter Abruf mit identischen Bytes erzeugt keine neue Version, sondern ein Audit-Ereignis `SOURCE_CHECKED_UNCHANGED`. Geänderte Bytes erzeugen eine neue, mit der Vorgängerin verknüpfte Version.

## Folgen
Ein Dritter kann mit `vcore verify --compare-official` jederzeit die aktuelle Datei des Herausgebers mit unserem Original vergleichen. Ein Unterschied ist kein Beweis für Manipulation, weil Herausgeber Dokumente aktualisieren, er wird aber sichtbar.
