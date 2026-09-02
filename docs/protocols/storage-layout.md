# Ablage-Layout (Stufe 1)

> **Status:** verbindlich ab BRIDGE-005. Grundlage: Konzept-Abschnitt 11.

Die Bridge legt Aufträge, Ergebnisse und die Auditspur als Dateien im Repository
ab (SSOT). Stufe 1 nutzt bewusst einfache, transparente Formate: YAML + Git,
Audit als JSON Lines.

## Verzeichnisse

```
tasks/
  BRIDGE-<id>/
    task.yaml                     # der Auftrag (gegen task.schema.yaml validiert)
results/
  BRIDGE-<id>/
    RUN-<yy>/
      result.yaml                 # Ergebnis eines Laufs (gegen result.schema.yaml)
audit/
  audit.jsonl                     # append-only Auditspur (1 JSON-Ereignis pro Zeile)
```

- `<id>` entspricht der `bridge_task_id` (z. B. `BRIDGE-0042`).
- `<yy>` ist die zweistellige Lauf-ID (`01`, `02`, …), passend zu `run_id`.
- Die Auditspur ist **append-only**: Ereignisse werden nur angehängt, nie
  geändert oder gelöscht. Jede Zeile validiert gegen `audit-event.schema.yaml`.

## Regeln (fail-closed)

- Schreiben nur innerhalb des Repos (`tasks/`, `results/`, `audit/`).
- Kein stilles Überschreiben: ein bereits existierender Auftrag oder Lauf wird
  nicht überschrieben, sondern abgelehnt.
- Ein Ergebnis muss sich auf einen existierenden Auftrag beziehen.
- Zustandswechsel nur über den Übergangs-Validator (BRIDGE-004); der
  Ereignistyp wird aus `audit-event-map.yaml` abgeleitet.
- Ungültige Task-/Result-Dateien (Schemafehler) werden abgelehnt; es wird nichts
  geschrieben.
