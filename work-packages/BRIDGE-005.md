# BRIDGE-005 — Ablage & Validierung (Herzstück Stufe 1)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-005 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-002, BRIDGE-003, BRIDGE-004 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code (HAM11) |

## Auftrag

Die Bridge soll Aufträge und Ergebnisse als Dateien ablegen, gegen die Schemas
validieren, Zustandsübergänge über den BRIDGE-004-Validator prüfen und die
Auditspur schreiben. Ablage-Layout: `docs/protocols/storage-layout.md`.

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/task.schema.yaml`, `schemas/result.schema.yaml` (Verträge)
- `schemas/state-model.yaml` + `src/bridge/state_machine.py` (Übergänge)
- `schemas/audit-event.schema.yaml` (Audit-Ereignis; erweitert)
- `schemas/audit-event-map.yaml` (SSOT: Zustand → event_type)
- `docs/protocols/storage-layout.md` (Ablage-Layout)

## Von Claude Code umzusetzen (Code-Logik)

### Sprache & Abhängigkeiten
- **Python 3**, Arbeit ausschließlich im repo-lokalen `.venv` (siehe CLAUDE.md).
- Abhängigkeiten in `requirements.txt` ergänzen: `pyyaml`, **`jsonschema`**.
  Installation nur nach Rückfrage, ins `.venv`.

### Modul `src/bridge/store.py`
Kapselt die gesamte Ablage/Validierung. Alle Pfade **parametrierbar**, damit
Tests hermetisch in einem Temp-Verzeichnis laufen (NICHT ins echte Repo schreiben):

- Klasse `Store(root=<repo>, schema_dir=root/"schemas")`.
  `root` bestimmt `tasks/`, `results/`, `audit/`; `schema_dir` die Schemas.
- Validierung gegen die YAML-Schemas mit `jsonschema` (Draft 2020-12),
  inkl. `format`-Prüfung für `date-time`.
- Methoden (fail-closed, klare Exceptions):
  - `validate(doc_or_path)` — erkennt `kind` (bridge_task/bridge_result) und
    validiert gegen das passende Schema.
  - `create_task(task)` — validiert, schreibt `tasks/<id>/task.yaml`
    (kein Überschreiben), setzt Status = `initial_state` (CREATED),
    hängt Audit-Ereignis `TASK_CREATED` an.
  - `load_task(id)` / `save_task(task)` — lesen/schreiben.
  - `set_status(id, new_state, actor, machine=None, reason=None)` —
    prüft Übergang via `state_machine.assert_transition`, aktualisiert Status,
    hängt Audit-Ereignis an; **event_type aus `audit-event-map.yaml`** ableiten
    (inkl. Sonderfall from_state_override), NICHT hartkodieren.
  - `next_run_id(id)` — ermittelt aus vorhandenen `results/<id>/RUN-*` das
    nächste `RUN-YY` (keine Ergebnisse → `RUN-01`), zweistellig.
  - `write_result(result)` — validiert, verlangt existierenden Auftrag,
    schreibt `results/<id>/RUN-<yy>/result.yaml` (kein Überschreiben eines
    vorhandenen Laufs), hängt Audit-Ereignis `RESULT_WRITTEN` an.
  - `append_audit(event)` — validiert das Ereignis gegen
    `audit-event.schema.yaml` und hängt es als eine JSON-Zeile an
    `audit/audit.jsonl` (append-only).
- **Fail-closed** überall: unbekannter Zustand, unerlaubter Übergang,
  Schemafehler, fehlender Auftrag, existierende Ziel-Datei, Pfad außerhalb
  `root` → Fehler, kein Schreiben.

### Minimale CLI (Ergonomie kommt in BRIDGE-006)
Aufruf `python src/bridge/store.py <cmd> ...`, Exit 0 = OK, != 0 = Fehler:
- `validate <pfad>`
- `create-task <task.yaml>`
- `set-status <BRIDGE-id> <NEW_STATE> --actor <a> [--machine <m>] [--reason <r>]`
- `write-result <result.yaml>`
- `next-run <BRIDGE-id>`
- `show <BRIDGE-id>`  (gibt aktuellen Status aus)

### Tests `tests/test_store.py` (stdlib `unittest`, hermetisch in tempdir)
Pflichtfälle:
- gültiger Auftrag → `create_task` schreibt Datei + Audit `TASK_CREATED`, Status CREATED
- ungültiger Auftrag (Pflichtfeld fehlt / unbekanntes Feld) → abgelehnt, nichts geschrieben
- `create_task` zweimal → zweiter Aufruf abgelehnt (kein Überschreiben)
- erlaubter Übergang CREATED→READY → Status aktualisiert + Audit `TASK_READY`
- unerlaubter Übergang CREATED→RUNNING → abgelehnt, Status unverändert, kein Audit
- Übergang AUS WAITING_FOR_RESUME → Audit-Ereignistyp `TASK_RESUMED` (Sonderfall)
- `next_run_id`: ohne Ergebnisse `RUN-01`, nach einem Ergebnis `RUN-02`
- gültiges Ergebnis → `write_result` schreibt Datei + Audit `RESULT_WRITTEN`
- Ergebnis für nicht existierenden Auftrag → abgelehnt
- Ergebnis für bereits vorhandenen Lauf → abgelehnt (kein Überschreiben)
- `audit.jsonl` ist append-only; jede Zeile validiert gegen das Audit-Schema
- kein Schreibzugriff außerhalb `root` (Pfad-Escaping wird abgelehnt)

### Abschluss
- `python -m unittest discover -s tests` grün (inkl. der BRIDGE-004-Tests).
- Pflicht-Footer ausgeben (`BRIDGE-005` + `RUN-YY` + Status).

## Scope

**Enthalten:** gelieferte Verträge/Layout (oben), `src/bridge/store.py`,
minimale CLI, `tests/test_store.py`, `requirements.txt` (+jsonschema),
README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** komfortables CLI-Gesamtwerkzeug → BRIDGE-006;
Result-Importer/Übernahme aus Codex → BRIDGE-007; Watcher → BRIDGE-008;
automatische Verknüpfung Ergebnis→Zustandswechsel (Orchestrierung) → später.

## Akzeptanzkriterien

- [ ] Aufträge/Ergebnisse werden validiert abgelegt (kein Überschreiben)
- [ ] Zustandswechsel nur über BRIDGE-004-Validator; event_type aus Map-Datei
- [ ] Auditspur append-only, jede Zeile schemakonform
- [ ] `next_run_id` deterministisch aus dem Dateisystem
- [ ] alle Tests grün, hermetisch (kein Schreiben ins echte Repo)
- [ ] fail-closed bei allen genannten Fehlerfällen
- [ ] Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-006 — CLI-Gesamtwerkzeug** (komfortable Kommandozeile über der Engine).
