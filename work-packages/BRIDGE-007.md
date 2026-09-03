# BRIDGE-007 — Result-Importer

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-007 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-003, BRIDGE-005, BRIDGE-006 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code (HAM11) |

## Auftrag

Ein Ergebnis aus dem tatsächlichen Executor-Kontext (Codex bzw. Claude Code)
strukturiert übernehmen und als valides `result.yaml` ablegen — statt es von
Hand zu schreiben. Der Importer ermittelt die **objektiven** Felder automatisch
aus Git und Umgebung und übernimmt nur die **subjektiven** aus einem Entwurf/Flag.

## Bereits vorhanden (nutzen, NICHT verändern)

- `src/bridge/store.py` — `Store` (`load_task`, `next_run_id`, `write_result`,
  `validate`). `write_result` erzwingt existierenden Auftrag, kein Überschreiben,
  Audit `RESULT_WRITTEN`.
- `schemas/result.schema.yaml` — Zielvertrag. Pflichtfelder:
  `schema_version, kind, bridge_task_id, project_id, run_id, status, repository,
  branch, head, executor, started_at, ended_at, created_by`.
- `src/bridge/cli.py` — wird um ein Subkommando erweitert.

## Von Claude Code umzusetzen

### Keine neue Abhängigkeit
Nur stdlib (`subprocess` für Git). Git-Zugriff **injizierbar** kapseln (siehe
Tests), damit die Tests hermetisch ohne echtes Git laufen.

### Modul `src/bridge/importer.py`
- `collect_git_info(root, base_head=None) -> dict` (Default-Implementierung mit
  echtem Git, read-only):
  - `repository` = Basisname von `git rev-parse --show-toplevel`
  - `branch`     = `git rev-parse --abbrev-ref HEAD`
  - `head`       = `git rev-parse HEAD`
  - `base_head`  = Argument oder `null`
  - `commits`    = wenn `base_head` gesetzt: Liste `{sha, message}` aus
    `git rev-list --reverse base_head..HEAD`; sonst `[]`
  - `changed_files` = wenn `base_head` gesetzt: `git diff --name-only base_head HEAD`;
    sonst Dateien des HEAD-Commits (`git diff-tree --no-commit-id --name-only -r HEAD`)
  - Bei Git-Fehler → Exception (fail-closed, nichts erfinden).
- `build_result(store, bridge_task_id, status, *, run_id=None, draft=None,
  base_head=None, executor="claude-code", machine=None, environment=None,
  runtime=None, model=None, reasoning_level=None, started_at=None,
  created_by=None, git_info_fn=collect_git_info) -> dict`:
  - lädt den Auftrag (`store.load_task`) → verifiziert Existenz, entnimmt `project_id`.
  - `run_id` = Argument oder `store.next_run_id(id)`.
  - Git-Provenienz aus `git_info_fn`.
  - `ended_at` = jetzt (UTC, RFC 3339); `started_at` = Argument/Entwurf oder = `ended_at`.
  - subjektive Felder aus `draft` (dict) + expliziten Argumenten (Argument
    gewinnt): `summary`, `acceptance_results`, `interruption_reason`,
    `resumable`, `resume_hint`.
  - `executor`/`machine`/`environment`/`runtime`/`model`/`reasoning_level`
    aus Argumenten (oder Umgebungsvariablen `BRIDGE_MACHINE`, `BRIDGE_ENV`,
    `BRIDGE_RUNTIME`, falls nicht gesetzt).
  - `created_by` = Argument oder `"<executor>@<machine|unknown>"`.
  - `schema_version="1.0"`, `kind="bridge_result"`.
  - Ergebnis-dict zusammensetzen und zurückgeben (noch nicht schreiben).
- `import_result(...)` = `build_result(...)` → `store.validate(result)` →
  `store.write_result(result)`. Fail-closed: Schemafehler/fehlender Auftrag/
  vorhandener Lauf → Fehler, kein Schreiben.

### CLI-Erweiterung in `src/bridge/cli.py`
- Neues Subkommando:
  `result import <BRIDGE-id> --status <STATE> [--from <draft.yaml>]
   [--base-head <sha>] [--run-id <RUN-YY>] [--executor <e>] [--machine <m>]
   [--environment <env>] [--runtime <rt>] [--summary <s>] [--started-at <ts>]`
  - `status` muss vorhanden sein (Flag oder Entwurf), sonst Usage-Fehler (Exit 2).
  - Erfolg → Exit 0 mit Pfad des geschriebenen Ergebnisses; Fachfehler → Exit 1.

### Tests `tests/test_importer.py` (stdlib unittest, hermetisch)
- Git-Zugriff über `git_info_fn`-Stub (fixe repository/branch/head/commits/
  changed_files) — **kein echtes Git nötig**.
- gültiger COMPLETED-Entwurf → `import_result` schreibt
  `results/<id>/RUN-01/result.yaml` + Audit `RESULT_WRITTEN`, Ergebnis valide
- `run_id` default = `next_run_id`; expliziter `run_id` wird beachtet
- `ended_at` automatisch (valides RFC 3339); `started_at` aus Entwurf übernommen
- `project_id` aus dem Auftrag übernommen (nicht neu eingegeben)
- Git-Felder korrekt aus dem Stub übernommen (head/branch/repository/commits/
  changed_files)
- INTERRUPTED ohne `interruption_reason`/`resumable` → fail-closed (Schema)
- INTERRUPTED mit Grund+resumable aus Entwurf → ok
- Import für nicht existierenden Auftrag → fail-closed
- CLI `result import ... --status COMPLETED` (mit Git-Stub) → Exit 0;
  ohne `--status` und ohne Entwurf → Exit 2

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Pflicht-Footer ausgeben (`BRIDGE-007` + `RUN-YY` + Status).

## Scope

**Enthalten:** `src/bridge/importer.py`, CLI-Erweiterung `result import`,
`tests/test_importer.py`, README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** Erkennen abgeschlossener Läufe (Watcher) → BRIDGE-008;
automatische Verknüpfung Ergebnis→Zustandswechsel → später/Runner.

## Akzeptanzkriterien

- [ ] Objektive Felder (Git/Umgebung/Zeit) automatisch ermittelt
- [ ] Subjektive Felder aus Entwurf/Flags übernommen (Flag gewinnt)
- [ ] `project_id`/`run_id` konsistent aus Auftrag bzw. `next_run_id`
- [ ] Ergebnis gegen Schema validiert und über die Engine abgelegt (kein Überschreiben)
- [ ] Git-Zugriff injizierbar; Tests hermetisch ohne echtes Git
- [ ] fail-closed bei Schemafehler/fehlendem Auftrag/vorhandenem Lauf/Git-Fehler
- [ ] alle Tests grün; Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-008 — Watcher** (erkennt abgeschlossene/steckengebliebene Läufe;
erste Automatisierung Richtung Stufe 2).
