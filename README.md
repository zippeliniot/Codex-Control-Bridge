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

## Zustandsmodell

Die gültigen Zustände und erlaubten Übergänge stehen verbindlich in
[`schemas/state-model.yaml`](schemas/state-model.yaml) (SSOT). Der ausführbare
Übergangs-Validator liegt in
[`src/bridge/state_machine.py`](src/bridge/state_machine.py) und liest die
Übergänge ausschließlich aus dieser Datei (keine hartkodierte Tabelle).

```
python src/bridge/state_machine.py CREATED READY    # -> ALLOWED  (Exit 0)
python src/bridge/state_machine.py CREATED RUNNING   # -> DENIED   (Exit 1)
```

Laufzeitabhängigkeit: `pyyaml` (siehe [`requirements.txt`](requirements.txt)).
Tests: `python -m unittest discover -s tests`.

---

## Ablage & Validierung

`src/bridge/store.py` legt Aufträge (`tasks/<id>/task.yaml`), Ergebnisse
(`results/<id>/RUN-<yy>/result.yaml`) und die append-only Auditspur
(`audit/audit.jsonl`) ab. Jedes Dokument wird gegen sein Schema geprüft
(`jsonschema`, Draft 2020-12), Zustandswechsel laufen über den
BRIDGE-004-Validator, der Audit-Ereignistyp stammt aus
[`schemas/audit-event-map.yaml`](schemas/audit-event-map.yaml). Layout:
[`docs/protocols/storage-layout.md`](docs/protocols/storage-layout.md).

```
python src/bridge/store.py create-task tasks/BRIDGE-042/task.yaml
python src/bridge/store.py set-status BRIDGE-042 READY --actor steuerprozess
python src/bridge/store.py next-run BRIDGE-042
```

---

## CLI

Einheitliches Werkzeug über der Engine (reine stdlib):

```
python src/bridge/cli.py --root . <kommando>     # aus dem Repo heraus
PYTHONPATH=src python -m bridge <kommando>        # alternativ
```

| Kommando | Zweck |
|---|---|
| `validate <pfad>` | Task/Result gegen Schema prüfen |
| `task create <task.yaml>` | Auftrag anlegen |
| `task show <BRIDGE-id>` | Status + Kernfelder |
| `task list` | alle Aufträge mit Status |
| `task set-status <id> <STATE> --actor <a> [--machine <m>] [--reason <r>]` | Zustandswechsel |
| `result write <result.yaml>` | Ergebnis ablegen |
| `result import <BRIDGE-id> --status <STATE> [--from <draft.yaml>] [--base-head <sha>] [--run-id <RUN-YY>] …` | Ergebnis aus dem Executor-Kontext übernehmen |
| `next-run <BRIDGE-id>` | nächste Lauf-ID |
| `audit show [<BRIDGE-id>]` | Auditspur (optional gefiltert) |
| `resume <BRIDGE-id>` | Wiederaufsetz-Hilfe (rein lesend) |
| `watch scan [--apply] [--actor <a>] [--machine <m>] [--task <id>]` | Ergebnisse/tote Heartbeats erkennen; mit `--apply` erlaubte Übergänge setzen |
| `watch loop --interval <sek> [--apply] [--actor <a>] [--machine <m>]` | dasselbe wiederholt (bis Ctrl+C) |
| `watch heartbeat <BRIDGE-id> <RUN-YY> [--actor <a>] [--machine <m>]` | Heartbeat eines Laufs schreiben/aktualisieren |
| `run start <BRIDGE-id> --actor <a> [--machine <m>]` | Lauf starten (→ RUNNING, initialer Heartbeat) |
| `run beat <BRIDGE-id> --actor <a> [--machine <m>]` | Heartbeat des aktuellen Laufs aktualisieren (an Checkpoints) |
| `run finish <BRIDGE-id> --status <STATE> [--from <draft.yaml>] [--base-head <sha>] --actor <a> [--summary <s>]` | Lauf abschließen: Ergebnis-Import + Zustandswechsel in einem Schritt |
| `run resume <BRIDGE-id> --actor <a> [--machine <m>]` | Lauf wiederaufnehmen (INTERRUPTED/WAITING_FOR_RESUME → RUNNING, neuer RUN) |

Exit-Codes: `0` ok, `1` Fachfehler/fail-closed, `2` Nutzungsfehler.

`result import` (`src/bridge/importer.py`) ermittelt die **objektiven** Felder
(Repository/Branch/HEAD, ggf. Commits und geänderte Dateien ab `--base-head`,
Zeitstempel, `project_id` aus dem Auftrag, `run_id` aus `next_run_id`)
automatisch und übernimmt nur die **subjektiven** aus `--from <draft.yaml>` bzw.
den Flags (Flag gewinnt). Der Git-Zugriff ist injizierbar (`git_info_fn`), die
Tests laufen hermetisch ohne echtes Git. Fail-closed bei Git-Fehler, fehlendem
Auftrag, Schemafehler oder bereits vorhandenem Lauf.

---

## Watcher (BRIDGE-008)

`src/bridge/watcher.py` beobachtet den Repo-Zustand und führt Aufträge in
`eligible_from_status` (Policy: [`schemas/watcher-policy.yaml`](schemas/watcher-policy.yaml))
automatisch weiter:

- **Ergebnis fertig** — `results/<id>/<letzter RUN>/result.yaml` vorhanden →
  Auftrag auf `on_result_status[<status>]`.
- **Heartbeat tot** — `now - last_seen > heartbeat_timeout_seconds` (oder kein
  Heartbeat jenseits einer Karenz seit Laufbeginn) → `on_stale_heartbeat.to_status`
  (nur Status + Audit-`reason`, **kein** `result.yaml`).

Trifft beides zu, hat „Ergebnis" Vorrang. Geschrieben wird **nur mit `--apply`**
(erfordert `--actor`); jeder Übergang muss laut Policy **und**
[`state-model.yaml`](schemas/state-model.yaml) erlaubt sein, sonst wird er
übersprungen (fail-closed). Der Watcher führt **niemals** Git-Aktionen aus. Die
Zeit (`now`) ist injizierbar → Tests hermetisch.

`src/bridge/heartbeat.py` schreibt/liest die Heartbeat-Datei
(`results/<id>/RUN-<yy>/heartbeat.json`, Schema
[`heartbeat.schema.yaml`](schemas/heartbeat.schema.yaml)); das periodische
Schlagen durch einen lebenden Executor übernimmt der Runner (BRIDGE-009).

```
python src/bridge/cli.py --root . watch scan
python src/bridge/cli.py --root . watch scan --apply --actor watcher
python src/bridge/cli.py --root . watch heartbeat BRIDGE-042 RUN-01 --actor codex
```

---

## Runner (BRIDGE-009)

`src/bridge/runner.py` orchestriert den Lauf-Lebenszyklus über die vorhandene
Engine — **ohne** selbst inhaltliche Arbeit oder Git zu tun:

- **`start`** — führt `CREATED→READY→CLAIMED→RUNNING` (nur fehlende Schritte,
  jeder auditiert), legt `run_id = next_run_id` an und schreibt den initialen
  Heartbeat.
- **`beat`** — aktualisiert den Heartbeat des aktuellen Laufs (nur im Status
  RUNNING); der Executor ruft dies an jedem Checkpoint/Commit.
- **`finish`** — ein Schritt: Übergang `RUNNING→<status>` zuerst per `is_allowed`
  prüfen, dann Ergebnis für den aktuellen Lauf über `importer.import_result`
  schreiben, dann `set_status`. Nicht erlaubter Übergang → Fehler, nichts
  geschrieben.
- **`resume`** — ein Schritt `INTERRUPTED→WAITING_FOR_RESUME→RUNNING`
  (Audit `TASK_WAITING_FOR_RESUME`, dann `TASK_RESUMED`), neuer `run_id`,
  frischer Heartbeat; zeigt offene Akzeptanzkriterien und `resume_hint` aus dem
  letzten Ergebnis.

Der Runner führt **niemals** Git-Aktionen aus. Zeit (`now`) und Git
(`git_info_fn`) sind injizierbar → Tests hermetisch.

```
python src/bridge/cli.py --root . run start  BRIDGE-042 --actor codex
python src/bridge/cli.py --root . run beat   BRIDGE-042 --actor codex
python src/bridge/cli.py --root . run finish BRIDGE-042 --status COMPLETED --actor codex --summary "…"
python src/bridge/cli.py --root . run resume BRIDGE-042 --actor codex
```

---

## Referenzprojekt Dorfschaft

Dorfschaft ist **ausschließlich** das erste spätere Referenz- und
Integrationsprojekt. Es wird während der Bridge-Entwicklung **nicht verändert
oder blockiert**. Die erste reale Integration ist ein reiner **Read-only-Test**.

Auftragsnummern bleiben strikt getrennt: `BRIDGE-xxx` (Bridge) vs. `DORF-xxx`
(Dorfschaft). Die Bridge speichert externe IDs, übernimmt aber nicht deren
Nummerierungslogik.
