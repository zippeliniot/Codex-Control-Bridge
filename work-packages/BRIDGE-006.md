# BRIDGE-006 — CLI-Gesamtwerkzeug

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-006 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-004, BRIDGE-005 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code (HAM11) |

## Auftrag

Eine komfortable, einheitliche Kommandozeile über der bestehenden Engine
(`src/bridge/store.py`, `src/bridge/state_machine.py`) bereitstellen. Die Engine
wird **wiederverwendet, nicht dupliziert**. Keine neue Laufzeitabhängigkeit
(nur stdlib `argparse`).

## Bereits vorhanden (nutzen, NICHT verändern)

- `src/bridge/store.py` — `Store(root, schema_dir=None)` mit `validate`,
  `create_task`, `load_task`, `set_status(task_id, new_state, actor, machine,
  reason)`, `next_run_id`, `write_result`, `append_audit`.
- `src/bridge/state_machine.py` — Übergangsprüfung.
- Schemas, `audit-event-map.yaml`, `docs/protocols/storage-layout.md`.

## Von Claude Code umzusetzen

### Dateien
1. `src/bridge/cli.py` — das Werkzeug. Kernfunktion `main(argv=None) -> int`,
   damit Tests es ohne Subprozess aufrufen können. Reine stdlib.
2. `src/bridge/__main__.py` — ruft `cli.main()`, damit `python -m bridge` läuft.
3. `tests/test_cli.py` — hermetische Tests (tempdir als `--root`).
4. README-Nachzug (Kommandoübersicht).

### Globale Optionen
- `--root <pfad>` (Standard: aktuelles Verzeichnis) — Basis für tasks/results/audit.
- `--schema-dir <pfad>` (Standard: `<root>/schemas`).
- Diese Optionen ermöglichen hermetische Tests und Betrieb aus dem Repo heraus.

### Subkommandos (Exit 0 = OK, 1 = Fachfehler/fail-closed, 2 = Nutzungsfehler)
- `validate <pfad>` — Task/Result gegen Schema prüfen.
- `task create <task.yaml>` — anlegen (delegiert an `create_task`).
- `task show <BRIDGE-id>` — aktuellen Status + Kernfelder ausgeben.
- `task list` — alle Aufträge unter `tasks/*/task.yaml` mit Status auflisten.
- `task set-status <BRIDGE-id> <NEW_STATE> --actor <a> [--machine <m>] [--reason <r>]`.
- `result write <result.yaml>` — Ergebnis ablegen (delegiert an `write_result`).
- `next-run <BRIDGE-id>` — nächste Lauf-ID ausgeben.
- `audit show [<BRIDGE-id>]` — Auditspur ausgeben; mit ID nach Auftrag gefiltert.
- `resume <BRIDGE-id>` — **Wiederaufsetz-Hilfe** (siehe unten).
- Fehlende/falsche Argumente → argparse-Usage, Exit 2.

### `resume`-Kommando (dockt an Checkpoint-Protokoll an)
Gibt kompakt aus, wo fortzusetzen ist:
- aktueller Status des Auftrags (aus `tasks/<id>/task.yaml`),
- nächste Lauf-ID (`next_run_id`),
- offene Akzeptanzkriterien: liest `work-packages/<id>.md`, listet Zeilen mit
  `- [ ]` (offen) und zählt `- [x]` (erledigt). Fehlt die Datei, klar vermerken.
- optional (best effort, wenn `git` verfügbar): die letzten Commits; bei Fehler
  einfach überspringen (kein harter Fehler).
Kein Schreibzugriff — `resume` ist rein lesend.

### Fehlerverhalten
- Fachfehler der Engine (SchemaValidationError, TransitionError, StoreError) →
  klare Meldung auf stderr, Exit 1. Kein Traceback für erwartbare Fehler.
- fail-closed bleibt erhalten: die CLI umgeht keine Engine-Prüfung.

### Tests `tests/test_cli.py` (stdlib unittest, hermetisch)
- `validate` gültig → 0; ungültig/fehlend → 1
- `task create` → 0 und Datei existiert; erneut → 1 (kein Überschreiben)
- `task list` listet angelegte Aufträge mit Status
- `task show` unbekannte ID → 1
- `set-status` erlaubt → 0 + Status geändert; unerlaubt → 1 + unverändert
- `result write` ok → 0; ohne Auftrag → 1
- `next-run` korrekt (RUN-01 → nach Ergebnis RUN-02)
- `audit show <id>` filtert nach Auftrag
- `resume <id>` zeigt Status, nächste Lauf-ID und offene `- [ ]`-Kriterien
- unbekanntes Subkommando / fehlendes Argument → Exit 2
- Aufrufe nutzen `main(argv=[...])` mit `--root <tempdir>` (kein echtes Repo)

### Abschluss
- `python -m unittest discover -s tests` grün (BRIDGE-004 + 005 + 006).
- Pflicht-Footer ausgeben (`BRIDGE-006` + `RUN-YY` + Status).

## Scope

**Enthalten:** `src/bridge/cli.py`, `src/bridge/__main__.py`,
`tests/test_cli.py`, README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** Result-Importer/Übernahme aus Codex → BRIDGE-007;
Watcher → BRIDGE-008; Projektprofile → BRIDGE-010.

## Akzeptanzkriterien

- [ ] Einheitliche CLI über der bestehenden Engine (keine Duplizierung)
- [ ] Alle Subkommandos vorhanden, konsistente Exit-Codes (0/1/2)
- [ ] `resume` zeigt Status, nächste Lauf-ID und offene Akzeptanzkriterien
- [ ] keine neue Laufzeitabhängigkeit (nur stdlib)
- [ ] erwartbare Fehler ohne Traceback, mit klarer Meldung
- [ ] alle Tests grün, hermetisch (kein Schreiben ins echte Repo)
- [ ] Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-007 — Result-Importer** (Ergebnis aus einem Codex-/Executor-Output
strukturiert übernehmen und ablegen).
