# Schemas

Verbindliche Schemas der Codex Control Bridge. Geschrieben als JSON Schema
(Draft 2020-12) in YAML-Form mit `additionalProperties: false` (fail-closed).

| Datei                 | Definiert in | Status |
|-----------------------|--------------|--------|
| `task.schema.yaml`    | BRIDGE-002   | vorhanden |
| `result.schema.yaml`  | BRIDGE-003   | offen |
| `project.schema.yaml` | BRIDGE-010   | offen |

Grundlage: Abschnitte 5 (Auftragsschema), 6 (Ergebnisformat) und 11
(Projektprofil) des Projektkonzepts.

Hinweis: Beispielaufträge und ein Validierungsskript sind bewusst noch nicht
Teil der Schema-Definition; sie folgen in BRIDGE-005 (Ablage/Validierung).
