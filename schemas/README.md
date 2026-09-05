# Schemas

Verbindliche Schemas der Codex Control Bridge. Geschrieben als JSON Schema
(Draft 2020-12) in YAML-Form mit `additionalProperties: false` (fail-closed).

| Datei                 | Definiert in | Status |
|-----------------------|--------------|--------|
| `task.schema.yaml`    | BRIDGE-002   | vorhanden |
| `result.schema.yaml`  | BRIDGE-003   | vorhanden |
| `project.schema.yaml` | BRIDGE-010   | offen |

Grundlage: Abschnitte 5 (Auftragsschema), 6 (Ergebnisformat) und 11
(Projektprofil) des Projektkonzepts.

Hinweis: Beispielaufträge und ein Validierungsskript sind bewusst noch nicht
Teil der Schema-Definition; sie folgen in BRIDGE-005 (Ablage/Validierung).

Zusätzlich (BRIDGE-004):

| Datei                      | Definiert in | Status |
|----------------------------|--------------|--------|
| `state-model.yaml`         | BRIDGE-004   | vorhanden |
| `audit-event.schema.yaml`  | BRIDGE-004   | vorhanden |

Zusätzlich (BRIDGE-005):

| Datei                     | Definiert in | Status |
|---------------------------|--------------|--------|
| `audit-event-map.yaml`    | BRIDGE-005   | vorhanden |

Zusätzlich (BRIDGE-008):

| Datei                     | Definiert in | Status |
|---------------------------|--------------|--------|
| `heartbeat.schema.yaml`   | BRIDGE-008   | vorhanden |
| `watcher-policy.yaml`     | BRIDGE-008   | vorhanden |

Zusätzlich (BRIDGE-011):

| Datei                          | Definiert in | Status |
|--------------------------------|--------------|--------|
| `git-readonly-allowlist.yaml`  | BRIDGE-011   | vorhanden |
