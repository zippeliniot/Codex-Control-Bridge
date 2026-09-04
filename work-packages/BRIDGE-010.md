# BRIDGE-010 — Projektprofile / Adapter (Schema + Loader)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-010 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-005, BRIDGE-006 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Auftrag

Projektspezifische Regeln aus dem Core herauslösen: ein Profil je Projekt unter
`projects/<id>/project.yaml`, validiert gegen ein Schema, über eine Laderoutine
bereitgestellt. BRIDGE-010 umfasst **nur Schema + Loader** — es wird noch NICHT
in Store/Runner verdrahtet (das folgt später/BRIDGE-011).

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/project.schema.yaml` — Vertrag (read_only ist Pflichtfeld).
- `projects/codex-control-bridge/project.yaml` — reales Profil der Bridge.
- `projects/examples/dorfschaft.project.yaml` — Beispiel/Vorlage (read-only).

## Von Claude Code umzusetzen (keine neue Abhängigkeit, nur stdlib + vorhandenes)

### Modul `src/bridge/profiles.py`
- `profile_path(root, project_id)` → `projects/<id>/project.yaml`.
- `load_profile(root, project_id, schema_dir=None) -> dict`:
  - lädt die Profildatei, validiert gegen `project.schema.yaml`
    (jsonschema, wie im Store), gibt das dict zurück.
  - Fehlt die Datei → `ProfileError` (fail-closed). Schemafehler → Fehler.
  - `project_id` im Profil muss zum Verzeichnisnamen passen; sonst Fehler.
- `list_profiles(root) -> list[str]`:
  - alle `projects/*/project.yaml` (Beispiele unter `projects/examples/` werden
    NICHT als echte Profile gezählt), sortiert.
- `validate_profile(path_or_doc, schema_dir)` — reine Validierung ohne Laden per ID.

### CLI-Erweiterung `src/bridge/cli.py`
- `project list` — bekannte Projekte (project_id + read_only + task_prefix).
- `project show <project_id>` — Kernfelder des Profils; unbekannt → Exit 1.
- `project validate <pfad>` — Profil validieren; ungültig → Exit 1.

### Tests `tests/test_profiles.py` (stdlib unittest, hermetisch)
- gültiges Profil laden → dict mit erwarteten Feldern
- fehlendes Profil → ProfileError (fail-closed)
- Schemafehler (read_only fehlt / unbekanntes Feld) → Fehler, nicht geladen
- project_id ≠ Verzeichnisname → Fehler
- `list_profiles` findet reale Profile, ignoriert `projects/examples/`
- CLI `project show` unbekannt → Exit 1; `project validate` ungültig → Exit 1

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Pflicht-Footer (`BRIDGE-010` + `RUN-YY` + Status).

## Scope

**Enthalten:** project.schema.yaml + Beispielprofile (geliefert),
`src/bridge/profiles.py`, CLI-Erweiterung `project`, `tests/test_profiles.py`,
README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** Verdrahtung in Store/Runner (task_prefix erzwingen,
allowed_machines/read_only prüfen) — bewusst später; realer Dorfschaft-Adapter
und Read-only-Integrationstest → BRIDGE-011/012.

## Akzeptanzkriterien

- [ ] Profil je Projekt unter projects/<id>/project.yaml, gegen Schema validiert
- [ ] `read_only` als Pflichtfeld erzwungen
- [ ] `load_profile`/`list_profiles`/`validate_profile` fail-closed
- [ ] project_id-Konsistenz mit Verzeichnisname geprüft
- [ ] Beispiele unter projects/examples/ nicht als echte Profile gezählt
- [ ] CLI `project list/show/validate` mit korrekten Exit-Codes
- [ ] alle Tests grün; Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-011 — Dorfschaft-Adapter (read-only)**, danach **BRIDGE-012 —
Read-only-Integrationstest**.
