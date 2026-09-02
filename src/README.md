# src/

Modultrennung des Bridge-Systems.

- `bridge/`   — Core: Task, Run, Result, Project, Machine, State, Permission, Event
  (implementiert: `state_machine.py` — Übergangs-Validator (BRIDGE-004);
  `store.py` — Ablage & Schema-Validierung (BRIDGE-005))
- `runner/`   — Ausführung eines Auftrags (Stufe 2+)
- `watcher/`  — Erkennung abgeschlossener Ergebnisse (Stufe 2+)
- `storage/`  — Ablage (Stufe 1: JSON/YAML+Git; später SQLite/PostgreSQL)
- `adapters/` — Projektadapter (z. B. dorfschaft, read-only)
