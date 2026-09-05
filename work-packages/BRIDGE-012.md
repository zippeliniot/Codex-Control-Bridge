# BRIDGE-012 — Read-only-Integrationstest (gegen ein echtes Repo)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-012 |
| project_id | codex-control-bridge |
| task_class | TEST / INTEGRATION |
| depends_on | BRIDGE-005, BRIDGE-007, BRIDGE-010, BRIDGE-011 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des CCB-Repos) |
| executor | claude-code |

## Auftrag

Beweisen, dass die Bridge ein **echtes** Git-Repo read-only begleiten kann, ohne
es zu verändern. Zielprojekt ist das **CCB-Repo selbst**; die Bridge-Ausgaben
(tasks/results/audit) gehen in ein **separates** Verzeichnis. Ergebnis: ein
ausführbares Integrationstest-Skript mit Unverändert-Nachweis.

## Fester Rahmen

- Kein WSL/Dorfschaft. Zielrepo = das lokale CCB-Repo (Windows-Seite).
- **Trennung lesen/schreiben:** Das beobachtete Repo wird NUR gelesen
  (über den Read-only-Adapter, BRIDGE-011). Alle Bridge-Schreibvorgänge landen
  in einem separaten Temp-/Ausgabe-`root`, NIE im Zielrepo.
- Der Test darf das Zielrepo nicht committen/ändern; HEAD und Working Tree
  müssen vorher/nachher identisch sein.

## Bereits vorhanden (nutzen, NICHT verändern)

- `src/bridge/adapter.py` (`ReadOnlyProjectAdapter`, `as_git_info_fn`)
- `src/bridge/importer.py` (`import_result`), `src/bridge/store.py` (`Store`)
- `schemas/` (Task-/Result-/…-Schemas)

## Von Claude Code umzusetzen (keine neue Abhängigkeit, nur stdlib)

### Skript `scripts/integration_readonly.py`
Ausführbar über den venv-Python. Ablauf:
1. `--target <pfad>` (Default: Wurzel des CCB-Repos, in dem das Skript liegt);
   `--out <pfad>` (Default: ein neues Temp-Verzeichnis) als separater Store-`root`.
2. **Vorher-Zustand** des Zielrepos erfassen: `head` (rev-parse HEAD) und
   `git status --porcelain`.
3. Read-only-Profil (inline, `read_only: true`) + `ReadOnlyProjectAdapter` auf
   das Zielrepo; Git-Stand nur lesend ermitteln.
4. Im **separaten** Store (`--out`): einen Beobachtungs-Auftrag anlegen
   (`Store.create_task`) und über `importer.import_result` mit
   `adapter.as_git_info_fn()` ein `result.yaml` ablegen (Provenienz aus dem
   Zielrepo). Kein Schreibzugriff auf `--target`.
5. **Nachher-Zustand** des Zielrepos erfassen.
6. **Nachweis**: `head` vorher == nachher UND `status --porcelain` unverändert.
   Zusätzlich: das erzeugte `result.yaml` liegt unter `--out`, sein `head`
   entspricht dem Zielrepo-HEAD.
7. Klarer Report + Exit-Code: `0` = PASS (Zielrepo unverändert, Ergebnis valide),
   `!= 0` = FAIL. Fail-closed bei jedem Fehler.

### Test `tests/test_integration_readonly.py` (stdlib unittest, hermetisch)
- Führt denselben Ablauf gegen ein **synthetisches** Temp-Git-Repo aus (damit die
  Suite überall grün bleibt, unabhängig vom CCB-Git-Stand):
  - Zielrepo unverändert (HEAD identisch), `result.yaml` mit korrekter Provenienz
    im separaten Store, kein Schreibzugriff aufs Zielrepo.
- Optional: ein Schreibversuch über den Adapter wird abgewiesen (Regressionsschutz).

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Real-Nachweis: `scripts/integration_readonly.py` gegen das CCB-Repo → PASS.
- Pflicht-Footer (`BRIDGE-012` + `RUN-YY` + Status).

## Scope

**Enthalten:** `scripts/integration_readonly.py`,
`tests/test_integration_readonly.py`, README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** echtes Dorfschaft/WSL; CLI-Verdrahtung des Adapters;
Stufe-2/3-Automatik über den bisherigen Umfang hinaus.

## Akzeptanzkriterien

- [ ] Skript beobachtet das echte CCB-Repo rein lesend (über den Adapter)
- [ ] Bridge-Ausgaben nur im separaten `--out`, nichts im Zielrepo
- [ ] Unverändert-Nachweis: HEAD und Working Tree des Zielrepos vorher == nachher
- [ ] erzeugtes `result.yaml` trägt die Provenienz des Zielrepos
- [ ] Exit-Code 0 bei PASS, != 0 bei FAIL (fail-closed)
- [ ] hermetischer unittest gegen synthetisches Repo grün
- [ ] alle Tests grün; Pflicht-Footer am Ende

## Abschluss des Programms

Mit BRIDGE-012 ist das geplante Programm (BRIDGE-001–012) vollständig: die Bridge
ist in Stufe 1 nutzbar, hat erste Stufe-2-Automatik (Watcher/Runner) und kann ein
reales Projekt read-only begleiten, ohne es zu verändern.
