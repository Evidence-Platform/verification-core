# ADR-0006 Hosting bei Infomaniak, modellagnostische LLM-Anbindung

Status: vorgeschlagen, 08.10.2026

## Entscheid
- Betrieb in der Infomaniak Public Cloud (Schweiz): Instanzen, PostgreSQL, S3-kompatibler Objektspeicher, später GPU-Instanz.
- Die Anwendung spricht Sprachmodelle nur über eine `LLMProvider`-Schnittstelle an (OpenAI-kompatibel).
- Entwicklung und Beta: Infomaniak AI Services (API). Produktion: selbst betriebenes Open-Weight-Modell (vLLM) auf einer GPU-Instanz, damit Modellgewichte per Hash fixiert und im Antwortprotokoll belegt werden können.
- Embeddings werden von Anfang an selbst betrieben und versioniert, weil sie bestimmen, welche Quellen gefunden werden.
- Die Modellwahl erfolgt erst nach Messung mit dem Evaluationsset.

## Offen
- Unterstützt die verwaltete PostgreSQL-Instanz von Infomaniak die Erweiterung pgvector? Falls nein, eigene Instanz.
- Bietet der Objektspeicher Object Lock?
- Kosten einer GPU-Instanz im Dauerbetrieb.
