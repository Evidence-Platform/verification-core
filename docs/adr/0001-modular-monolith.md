# ADR-0001 Modularer Monolith in Python

Status: angenommen, 08.10.2026

## Kontext
Das MVP braucht Dokumentenverarbeitung, Kryptografie, eine öffentliche API und später RAG. Das Team ist klein, ein grosser Teil des Codes entsteht agentisch.

## Entscheid
Ein modularer Monolith in Python (FastAPI, SQLAlchemy 2, Alembic). Module sind als Python-Pakete getrennt und kommunizieren über Funktionen, nicht über das Netz. Getrennte Prozesse nur dort, wo es technisch nötig ist (Webfrontend, Worker, Modellserver, Datenbank).

## Folgen
Ein Deployment, eine Transaktion pro Import, einfaches Debugging. Ein Modul lässt sich später als Dienst herauslösen, weil es keine fremden Tabellen direkt beschreibt.
