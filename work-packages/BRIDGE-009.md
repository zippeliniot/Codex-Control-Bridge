# BRIDGE-009 — Runner & Resume-Orchestrierung

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-009 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-005, BRIDGE-006, BRIDGE-007, BRIDGE-008 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Auftrag

Eine Lauf-Lebenszyklus-Orchestrierung: ein `run`-Kommando, das einen Lauf
**startet, begleitet (Heartbeat), abschließt und wiederaufnimmt** — mit den
vorhandenen Bausteinen. Der Runner ist KEIN KI-Executor; die inhaltliche Arbeit
macht weiterhin Claude Code/Codex.

## Sicherheits-Leitplanken (verbindlich)

1. **Nie Git.** Kein commit/push/merge. Nur `task.yaml`, `result.yaml`,
   Heartbeat und Auditspur werden geschrieben; Committen/Pushen bleibt beim Menschen.
2. **Nur erlaubte Übergänge**, jeweils über `state_machine`/`Store.set_status`.
3. **Fail-closed.** Auftrag im falschen Zustand, mehrdeutige Lage → Fehler.

## Bereits vorhanden (nutzen, NICHT verändern)

- `src/bridge/store.py` (`load_task`, `set_status`, `next_run_id`, `validate`)
- `src/bridge/importer.py` (`import_result`, `collect_git_info`, `git_info_fn`)
- `src/bridge/heartbeat.py` (`beat`, `read_heartbeat`, `heartbeat_path`)
- `src/bridge/state_machine.py`; `schemas/state-model.yaml`

## Von Claude Code umzusetzen (keine neue Abhängigkeit, nur stdlib)

### Modul `src/bridge/runner.py`
- `current_run_id(store, id)` — höchstes vorhandenes `results/<id>/RUN-*`
  (oder None).
- `start(store, id, actor, machine=None, now=…) -> run_id`:
  - zulässig nur, wenn Status in {CREATED, READY, CLAIMED}; sonst Fehler.
  - führt den Auftrag über die feste Kette CREATED→READY→CLAIMED→RUNNING bis
    RUNNING (nur die fehlenden Schritte, jeder via `set_status`, jeder auditiert).
  - `run_id = store.next_run_id(id)`; initialen Heartbeat schreiben
    (`heartbeat.beat`).
  - Rückgabe/Ausgabe: `run_id`, Status, offene Akzeptanzkriterien (aus
    `work-packages/<id>.md`, falls vorhanden).
- `beat(store, id, actor=None, machine=None, now=…)`:
  - aktueller Lauf = `current_run_id`; nur wenn Status RUNNING; Heartbeat
    aktualisieren. (Executor ruft dies an jedem Checkpoint/Commit.)
- `finish(store, id, status, *, draft=None, base_head=None, actor, machine=None,
  git_info_fn=…, now=…, **prov)`:
  - **ein Schritt**: Zielübergang RUNNING→`status` zuerst auf Zulässigkeit
    prüfen (`is_allowed`); dann Ergebnis für den aktuellen Lauf über
    `importer.import_result(...)` schreiben; dann `store.set_status(id, status,
    actor, machine, reason)`. Bei nicht erlaubtem Übergang → Fehler, nichts
    schreiben.
- `resume(store, id, actor, machine=None, now=…) -> run_id`:
  - zulässig, wenn Status INTERRUPTED oder WAITING_FOR_RESUME.
  - **ein Schritt**: INTERRUPTED→WAITING_FOR_RESUME→RUNNING (fehlende Schritte,
    Audit `TASK_WAITING_FOR_RESUME` dann `TASK_RESUMED`).
  - neuer `run_id = store.next_run_id(id)`; frischen Heartbeat schreiben.
  - Ausgabe: neuer `run_id`, offene Akzeptanzkriterien, `resume_hint` aus dem
    letzten Ergebnis (falls vorhanden).

### CLI-Erweiterung `src/bridge/cli.py`
- `run start <BRIDGE-id> --actor <a> [--machine <m>]`
- `run beat <BRIDGE-id> [--actor <a>] [--machine <m>]`
- `run finish <BRIDGE-id> --status <STATE> [--from <draft.yaml>]
   [--base-head <sha>] [--actor <a>] [--machine <m>] [--summary <s>]`
- `run resume <BRIDGE-id> --actor <a> [--machine <m>]`
- schreibende Kommandos erfordern `--actor`, sonst Exit 2.

### Tests `tests/test_runner.py` (stdlib unittest, hermetisch, Zeit + git injiziert)
- `start` auf CREATED → Status RUNNING, RUN-01-Heartbeat existiert, Audit-Kette
- `start` auf bereits RUNNING → Fehler (fail-closed)
- `beat` aktualisiert `last_seen` des aktuellen Laufs
- `finish` COMPLETED (mit git-Stub) → `results/<id>/RUN-01/result.yaml` +
  Status COMPLETED + Audit `TASK_COMPLETED`
- `finish` mit nicht erlaubtem Zielübergang → Fehler, nichts geschrieben
- `resume` auf INTERRUPTED → Status RUNNING, neuer Lauf RUN-02, neuer Heartbeat,
  Audit `TASK_WAITING_FOR_RESUME` + `TASK_RESUMED`
- `resume` auf nicht-fortsetzbarem Status → Fehler
- Zusammenspiel `next_run_id`/`current_run_id` über start→finish→resume korrekt

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Pflicht-Footer (`BRIDGE-009` + `RUN-YY` + Status).

## Scope

**Enthalten:** `src/bridge/runner.py`, CLI-Erweiterung `run`,
`tests/test_runner.py`, README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** ereignisbasierte Steuerkette / Webhooks (Stufe 3);
Projektprofile → BRIDGE-010.

## Akzeptanzkriterien

- [ ] `run start/beat/finish/resume` vorhanden und über die Engine umgesetzt
- [ ] `finish` = ein Schritt (Import + Zustandswechsel), fail-closed bei
      unerlaubtem Übergang
- [ ] `resume` fährt INTERRUPTED→WAITING_FOR_RESUME→RUNNING in einem Schritt,
      neue RUN-ID, frischer Heartbeat
- [ ] Heartbeat an Checkpoints koppelbar (`run beat`)
- [ ] Runner führt nie Git-Aktionen aus
- [ ] Zeit/Git injizierbar; Tests hermetisch
- [ ] alle Tests grün; Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-010 — Projektprofile/Adapter** (projektspezifische Regeln außerhalb des
Core; Vorbereitung der Dorfschaft-Read-only-Integration).
