# BRIDGE-013 — Profil um executor/controller erweitern (Schema + Loader)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-013 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-010 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Auftrag

Das Projektprofil trägt künftig zwei neue Felder, damit die spätere Steuerkonsole
(Stufe 3) **datengetrieben** weiß, wer ausführt und wer steuert:
`executor` (codex | claude-code | null) und `controller`
(anthropic | openai | human | null). Der Loader stellt sie bequem bereit.

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/project.schema.yaml` — um `executor`/`controller` erweitert (Enums,
  optional, additionalProperties bleibt false).
- `projects/codex-control-bridge/project.yaml` — `executor: claude-code`,
  `controller: human`.
- `projects/examples/dorfschaft.project.yaml` — `executor: null`,
  `controller: null` (nur beobachtet).

## Von Claude Code umzusetzen (keine neue Abhängigkeit, nur stdlib + vorhandenes)

### Ergänzung in `src/bridge/profiles.py`
- `get_executor(profile) -> str | None` — liefert `profile.get("executor")`.
- `get_controller(profile) -> str | None` — liefert `profile.get("controller")`.
- `requires_automation(profile) -> bool` — True, wenn `executor` gesetzt (nicht
  null) und `read_only` False ist (ein beobachtetes read-only-Projekt wird nicht
  ausgeführt).
- Keine Änderung an `load_profile`/Validierung nötig (Schema erzwingt die Werte).

### CLI (optional, minimal)
- `project show <id>` soll `executor` und `controller` mit ausgeben.

### Tests `tests/test_profiles.py` erweitern
- Profil mit `executor: claude-code`/`controller: human` lädt; Accessoren liefern
  die Werte.
- ungültiger `executor` (z. B. `gemini`) / `controller` → Validierungsfehler
  (fail-closed), nicht geladen.
- `executor: null` ist zulässig; `get_executor` → None; `requires_automation`
  für ein read-only-Profil → False.

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Pflicht-Footer (`BRIDGE-013` + `RUN-YY` + Status).

## Scope

**Enthalten:** Schema-Erweiterung + Profil-Updates (geliefert),
Accessoren in `profiles.py`, `project show`-Erweiterung, Test-Ergänzungen,
README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** Executor-/Controller-Implementierungen → BRIDGE-014 ff.

## Akzeptanzkriterien

- [x] `executor`/`controller` im Schema (Enums, optional, fail-closed)
- [x] Profile aktualisiert und valide
- [x] `get_executor`/`get_controller`/`requires_automation` vorhanden
- [x] ungültige Werte werden abgewiesen
- [x] `project show` zeigt executor/controller
- [x] alle Tests grün; Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-014 — Executor-Abstraktion + Claude-Code-Executor (CLI-getrieben).**
