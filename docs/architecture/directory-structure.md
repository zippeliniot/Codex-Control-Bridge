# Verzeichnisstruktur

Basierend auf Abschnitt 18 des Projektkonzepts. Verbindlich ab BRIDGE-001.

```
codex-control-bridge/
│
├── README.md
│
├── docs/
│   ├── architecture/     # Architekturgrundlage, Struktur (verbindlich)
│   ├── concepts/         # Detailkonzepte (Task-Identität, Zustände, Resume …)
│   ├── protocols/        # Übergabeprotokoll, Dateilayout Stufe 1
│   ├── security/         # Rechte-, Git-, Fail-closed-Modell (verbindlich)
│   └── handover/         # Handover-Regeln, SSOT-Prinzip (verbindlich)
│
├── schemas/              # Inhalt kommt in BRIDGE-002/003/010
│   ├── task.schema.json      (BRIDGE-002)
│   ├── result.schema.json    (BRIDGE-003)
│   └── project.schema.json   (BRIDGE-010)
│
├── projects/
│   └── examples/         # Beispiel-Projektprofile als Vorlage (BRIDGE-010)
│
├── src/
│   ├── bridge/           # Core: Task/Run/Result/State/Permission/Event
│   ├── runner/           # Ausführung (Stufe 2+)
│   ├── watcher/          # Ergebniserkennung (Stufe 2+)
│   ├── storage/          # Ablage: JSON/YAML+Git → später SQLite/PostgreSQL
│   └── adapters/         # Projektadapter (z. B. dorfschaft, read-only)
│
├── tests/                # Tests
│
├── scripts/              # Hilfsskripte (CLI-Wrapper etc.)
│
└── work-packages/        # Auftragsdokumentation BRIDGE-xxx
```

## Anmerkungen

- Leere Verzeichnisse werden per `.gitkeep` versioniert, damit die Struktur im
  Repository sichtbar bleibt.
- `schemas/` ist in BRIDGE-001 bewusst **ohne Schema-Inhalt**. Die
  Schema-Definition erfolgt in BRIDGE-002 (Task) und BRIDGE-003 (Result); das
  Projektschema in BRIDGE-010.
- `src/` enthält in Stufe 0/1 noch keine produktive Logik; die Unterordner
  bilden die spätere Modultrennung ab.
