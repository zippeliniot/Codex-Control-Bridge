# src/

Modultrennung des Bridge-Systems. In Stufe 0/1 noch ohne produktive Logik.

- `bridge/`   — Core: Task, Run, Result, Project, Machine, State, Permission, Event
- `runner/`   — Ausführung eines Auftrags (Stufe 2+)
- `watcher/`  — Erkennung abgeschlossener Ergebnisse (Stufe 2+)
- `storage/`  — Ablage (Stufe 1: JSON/YAML+Git; später SQLite/PostgreSQL)
- `adapters/` — Projektadapter (z. B. dorfschaft, read-only)
