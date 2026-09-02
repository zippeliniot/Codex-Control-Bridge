# BRIDGE-003 — Result-Schema definieren

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-003 |
| project_id | codex-control-bridge |
| task_class | ARCHITECTURE |
| permission | READ_ONLY + WORKTREE_WRITE (nur Neuanlage der Schema-Datei) |
| depends_on | BRIDGE-002 |
| status | COMPLETED (Ergebnisvertrag erfüllt) |

## Auftrag

Den formalen, maschinenprüfbaren Ergebnisvertrag ("bridge_result") gemäß
Konzept-Abschnitt 6 als Schema definieren — Gegenstück zum Task-Schema.

## Entscheidungen

- Gleiche Bauart wie BRIDGE-002: JSON Schema (Draft 2020-12) als kommentiertes
  YAML mit `additionalProperties: false` (fail-closed).
- **Verknüpfung Auftrag ↔ Lauf** über `bridge_task_id` + `run_id`.
- **Fail-closed-Bedingung** (if/then): `status=INTERRUPTED` verlangt zwingend
  `interruption_reason` und `resumable`.
- `run_id` folgt der in CLAUDE.md verankerten Lauf-Logik (`RUN-01`, `RUN-02`, …).
- Git- und Ausführungs-Provenienz sowie optionale Integritäts-Hashes
  (`task_hash`, `result_hash`, `diff_hash`) aufgenommen (Konzept-Abschnitt 10).

## Scope

**Enthalten:** `schemas/result.schema.yaml`, README-Nachzug, dieses Arbeitspaket.

**Bewusst NICHT enthalten:** Beispiel/Validierung/Ablage → BRIDGE-005;
Zustandsübergänge/Audit → BRIDGE-004; Projektschema → BRIDGE-010.

## Ergebnisvertrag

`schemas/result.schema.yaml` mit: Meta (`schema_version`, `kind`), Verknüpfung
(`bridge_task_id`, `project_id`, `project_task_id`), Lauf (`run_id`,
`started_at`, `ended_at`), Ausgang (`status`, `summary`, `acceptance_results`),
Unterbrechung/Resume (`interruption_reason`, `resumable`, `resume_hint`),
Git-Provenienz (`repository`, `branch`, `base_head`, `head`, `pushed`,
`commits`, `changed_files`), Integrität (`task_hash`, `result_hash`,
`diff_hash`), Ausführungs-Provenienz (`executor`, `physical_machine`,
`environment`, `runtime`, `model`, `reasoning_level`), Provenienz (`created_by`).

## Akzeptanzkriterien

- [x] Gültiges JSON Schema Draft 2020-12 (Meta-Schema-Check bestanden)
- [x] `additionalProperties: false` auf allen Objektebenen
- [x] COMPLETED-Ergebnis validiert
- [x] `INTERRUPTED` ohne Ursache wird abgelehnt (if/then, fail-closed)
- [x] `INTERRUPTED` mit Ursache validiert
- [x] Unbekanntes Feld wird abgelehnt
- [x] Falsches `run_id`-Muster wird abgelehnt
- [x] Nur Schema-Definition (kein Beispiel/Validator im Scope)

## Nächster Auftrag

**BRIDGE-004 — Zustandsmodell & Übergänge** (Konzept-Abschnitt 7) oder nach
Programmreihenfolge festzulegen.
