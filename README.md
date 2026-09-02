# Codex Control Bridge (CCB)

**Projekt-ID:** CCB
**Arbeitsname:** Codex Control Bridge
**Status:** In Entwicklung — Stufe 0/1
**Auftragsnummerierung:** `BRIDGE-001`, `BRIDGE-002`, `BRIDGE-003`, …

Die **Codex Control Bridge** ist eine **projektunabhängige Vermittlungsschicht**
für strukturierte Aufträge und Ergebnisse zwischen einem **Steuerprozess**
(z. B. ein ChatGPT-Steuerchat, später auch CLI/API/Weboberfläche) und **Codex**
als ausführender Instanz.

Sie standardisiert und automatisiert schrittweise die heute manuellen Übergaben:

```
Steuerprozess → strukturierter Auftrag → Bridge → Codex
             → strukturiertes Ergebnis → Bridge → Steuerprozess
```

Die Bridge **transportiert und verwaltet** Aufträge, Läufe und Ergebnisse.
Die **fachliche Steuerung bleibt beim Steuerprozess bzw. beim Menschen.**

---

## Kernprinzipien (verbindlich)

Diese Prinzipien sind für **alle** Arbeitspakete bindend. Details in
[`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

1. **Projektunabhängigkeit** — der Core enthält keine Fachlogik eines konkreten
   Projekts. Projektbezogene Regeln kommen über Projektprofile/Adapter.
2. **SSOT im Repository** — Auftrag, Zustand und Ergebnis müssen außerhalb des
   Chatverlaufs reproduzierbar auffindbar sein. Kein Clipboard, keine
   Chat-History, kein reiner Einzelrechner-Zustand als alleinige Quelle.
3. **Fail-closed** — bei Unsicherheit `BLOCKED`, niemals improvisieren.
4. **Least privilege** — Default `READ_ONLY`. Erweiterte Rechte nur explizit im
   Auftrag. Kritische Aktionen (MERGE, DEPLOY, DATABASE_WRITE, FORCE_PUSH) nie
   implizit.
5. **Eindeutige Identität** — jeder Auftrag hat eine systemweit eindeutige
   `bridge_task_id`; die projektspezifische ID bleibt separat erhalten.
6. **Handover-Fähigkeit** — vollständig rechnerunabhängig übergabefähig.

---

## Verzeichnisstruktur

Siehe [`docs/architecture/directory-structure.md`](docs/architecture/directory-structure.md).

```
codex-control-bridge/
├── docs/            # Architektur, Konzepte, Protokolle, Sicherheit, Handover
├── schemas/         # Task-/Result-/Project-Schema (Inhalt: BRIDGE-002/003/010)
├── projects/        # Projektprofile (Adapter) — examples/ als Vorlage
├── src/             # Implementierung: bridge, runner, watcher, storage, adapters
├── tests/           # Tests
├── scripts/         # Hilfsskripte
└── work-packages/   # Auftragsdokumentation BRIDGE-xxx
```

---

## Entwicklungsstand

| Stufe | Ziel | Status |
|-------|------|--------|
| Stufe 0 | Architektur & Protokoll (Schemas, Zustands-, Resume-, Rechte-, Auditmodell) | in Arbeit |
| Stufe 1 | Datei-/Repository-basierte Bridge (bereits produktiv nutzbar) | offen |
| Stufe 2 | Watcher + automatischer Runner | offen |
| Stufe 3 | Ereignisbasierte Steuerkette | offen |

Arbeitspakete: siehe [`work-packages/`](work-packages/).

---

## Referenzprojekt Dorfschaft

Dorfschaft ist **ausschließlich** das erste spätere Referenz- und
Integrationsprojekt. Es wird während der Bridge-Entwicklung **nicht verändert
oder blockiert**. Die erste reale Integration ist ein reiner **Read-only-Test**.

Auftragsnummern bleiben strikt getrennt: `BRIDGE-xxx` (Bridge) vs. `DORF-xxx`
(Dorfschaft). Die Bridge speichert externe IDs, übernimmt aber nicht deren
Nummerierungslogik.
