# BRIDGE-011 — Dorfschaft-Adapter (read-only, Mechanismus)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-011 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-007, BRIDGE-010 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des CCB-Repos) |
| executor | claude-code |

## Auftrag

Einen **read-only-Projektadapter** bauen, der den Git-Stand eines fremden
Projekts (Dorfschaft) liest, ohne je zu schreiben. `read_only: true` aus dem
Profil (BRIDGE-010) wird **hart** erzwungen: nur Kommandos aus der Allowlist,
alles andere abgelehnt.

## Fester Rahmen (nicht verhandelbar)

- **Nur Mechanismus + hermetische Tests.** KEINE Verbindung zum echten
  Dorfschaft in diesem Paket (das ist BRIDGE-012, auf der Codex/Ubuntu-Seite).
- Tests laufen gegen ein **synthetisches Wegwerf-Git-Repo** im Temp-Verzeichnis.
- Der Adapter schreibt **nie** ins fremde Repo; keine WSL-/Dorfschaft-Zugriffe
  durch Claude Code.

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/git-readonly-allowlist.yaml` — SSOT der erlaubten Lese-Kommandos.
- `src/bridge/profiles.py` (`load_profile`), `src/bridge/importer.py`
  (`import_result`, git_info_fn-Schnittstelle).

## Von Claude Code umzusetzen (keine neue Abhängigkeit, nur stdlib)

### Modul `src/bridge/adapter.py`
- `load_allowlist(schema_dir) -> set[str]` — liest die Allowlist-Datei.
- `ReadOnlyViolation(Exception)`, `AdapterError(Exception)`.
- `run_readonly_git(repo_path, args, *, allowlist) -> str`:
  - `args[0]` (das Subkommando) muss in der Allowlist sein, sonst
    `ReadOnlyViolation` — **bevor** irgendetwas ausgeführt wird.
  - führt `git -C <repo_path> <args...>` aus, gibt stdout zurück;
    git-Fehler → `AdapterError`.
  - Der Adapter baut Kommandos ausschließlich selbst aus festen Lese-Argumenten.
- Klasse `ReadOnlyProjectAdapter(profile, repo_path, schema_dir=None)`:
  - `__init__`: verlangt `profile["read_only"] is True`, sonst `ReadOnlyViolation`
    ("Adapter nur für read_only-Projekte").
  - `git_info(base_head=None) -> dict` mit denselben Feldern wie
    `importer.collect_git_info` (`repository`, `branch`, `head`, `base_head`,
    `commits`, `changed_files`) — ausschließlich über Allowlist-Kommandos
    (Branch via `rev-parse --abbrev-ref HEAD`).
  - `as_git_info_fn()` → Callable `(root=None, base_head=None)`, das `root`
    ignoriert und `repo_path` nutzt — direkt als `git_info_fn` für den Importer
    verwendbar (Ergebnis landet im CCB-Store, Provenienz kommt aus Dorfschaft).

### Tests `tests/test_adapter.py` (stdlib unittest, hermetisch, echtes Temp-Git)
- baut ein synthetisches Git-Repo (git init + Commits) als „fremdes" Projekt
- `git_info()` liefert korrekten `head` (== `git rev-parse HEAD`), Branch, Commits
- **write-Kommando abgelehnt**: `run_readonly_git(repo,["commit","-m","x"],...)`
  → `ReadOnlyViolation`; das Repo bleibt **unverändert** (HEAD identisch)
- weitere abgelehnte: `push`, `checkout`, `reset`, `add` → `ReadOnlyViolation`
- Adapter mit `read_only: false`-Profil → `ReadOnlyViolation` im `__init__`
- Allowlist wird aus der YAML geladen (nicht hartkodiert)
- **Integration**: `adapter.as_git_info_fn()` mit `importer.import_result` gegen
  einen CCB-Store (separates Temp-`root`) → valides `result.yaml` mit
  Dorfschaft-Provenienz; das fremde Repo bleibt unverändert

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Pflicht-Footer (`BRIDGE-011` + `RUN-YY` + Status).

## Scope

**Enthalten:** git-readonly-allowlist.yaml (geliefert), `src/bridge/adapter.py`,
`tests/test_adapter.py`, README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** Verbindung zum echten Dorfschaft-Repo, CLI-Verdrahtung,
Betrieb → BRIDGE-012 (Read-only-Integrationstest, Codex/Ubuntu-Seite).

## Akzeptanzkriterien

- [x] Adapter liest Git-Stand nur über Allowlist-Kommandos
- [x] jedes Nicht-Allowlist-Kommando → ReadOnlyViolation, fremdes Repo unverändert
- [x] `read_only: false`-Profil wird abgelehnt
- [x] Allowlist aus der YAML geladen (nicht hartkodiert)
- [x] `as_git_info_fn` speist den Importer; Ergebnis im CCB-Store, Provenienz aus fremdem Repo
- [x] Tests hermetisch (synthetisches Temp-Git), fremdes Repo bleibt unverändert
- [x] alle Tests grün; Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-012 — Read-only-Integrationstest** gegen das echte Dorfschaft
(auf der Codex/Ubuntu-Seite, rein lesend).
