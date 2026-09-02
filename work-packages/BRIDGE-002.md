# BRIDGE-002 — Task-Schema definieren

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-002 |
| project_id | codex-control-bridge |
| task_class | ARCHITECTURE |
| permission | READ_ONLY + WORKTREE_WRITE (nur Neuanlage der Schema-Datei) |
| depends_on | BRIDGE-001 |
| status | COMPLETED (Ergebnisvertrag erfüllt) |

## Auftrag

Den formalen, maschinenprüfbaren Auftragsvertrag ("bridge_task") gemäß
Konzept-Abschnitt 5 als Schema definieren.

## Entscheidungen

- **Format:** YAML (lesbar, kommentierbar).
- **Strenge:** JSON Schema (Draft 2020-12) mit `additionalProperties: false`
  → unbekannte/vertippte Felder werden fail-closed abgelehnt. Bewusst gegen ein
  reines „Pflichtfelder-Doku"-Modell entschieden, damit Validator (BRIDGE-005),
  Watcher und Runner den Vertrag durchsetzen können.
- **permissions:** als explizite Liste (feingranular, least privilege).
- **status:** verbleibt im Auftrag als aktueller Zeiger; Übergänge in BRIDGE-004.
- **depends_on:** aufgenommen (Reihenfolgen), kostet nichts.

## Scope

**Enthalten:**
- `schemas/task.schema.yaml` (Schema-Definition)
- `schemas/README.md` (Referenz `.json` → `.yaml`, Status)
- `work-packages/BRIDGE-002.md`

**Bewusst NICHT enthalten (spätere Arbeitspakete):**
- Beispielauftrag, Validierungsskript, Ablage → BRIDGE-005
- Result-Schema → BRIDGE-003
- Zustandsübergänge → BRIDGE-004
- Projektschema → BRIDGE-010

## Ergebnisvertrag

`schemas/task.schema.yaml` mit Feldern: Meta (`schema_version`, `kind`),
Identität (`bridge_task_id`, `project_id`, `project_task_id`), Beschreibung
(`title`, `description`, `task_class`, `acceptance_criteria`), Ziel/Kontext
(`repository`, `branch`, `git`), Rechte (`permissions`), Ausführung
(`target_environment`, `model`, `reasoning_level`), Status/Provenienz
(`status`, `created_at`, `created_by`, `depends_on`).

## Akzeptanzkriterien

- [x] Gültiges JSON Schema Draft 2020-12 (Meta-Schema-Check bestanden)
- [x] `additionalProperties: false` auf Objektebenen
- [x] Beispielauftrag validiert
- [x] Unbekanntes Feld wird abgelehnt (Gegentest)
- [x] Leere `permissions` wird abgelehnt (Gegentest)
- [x] Nur Schema-Definition (kein Beispiel/Validator im Scope)

## Nächster Auftrag

**BRIDGE-003 — Result-Schema definieren** (Konzept-Abschnitt 6).
