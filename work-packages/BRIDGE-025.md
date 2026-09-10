# BRIDGE-025 — CLI härten: automatischer Commit für Store-Aktionen + korrekte changed_files-Herkunft

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0025 |
| project_id | codex-control-bridge |
| task_class | BUGFIX |
| depends_on | BRIDGE-0024 (ARCHIVED) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe HOCH — Eingriff in `importer.py`/`cli.py` (Kernmechanik, nicht nur Web-UI), zwei getrennte Root-Causes, Wiederverwendung sicherheitskritischer Logik aus BRIDGE-024. |

> **Verbindlich für diesen und jeden CCB-Auftrag:**
> - Jede Zustandsänderung läuft über die Bridge-CLI
>   (`bridge task create` / `bridge run start` / `bridge run beat` /
>   `bridge run finish`) — niemals direktes Bearbeiten von Dateien im
>   Store, um einen Status zu simulieren.
> - Dieser Auftrag trägt `GIT_PUSH` im Berechtigungsprofil. Nach
>   `run finish` **muss** `git push` ausgeführt werden — ohne Push kann
>   der Steuerchat das Ergebnis nicht per frischem Klon abrufen und
>   verifizieren (Regel 6 der Übergabe).
> - **Für diesen Auftrag selbst gilt eine Ausnahme von der bisherigen
>   Praxis:** Ab dem Zeitpunkt, an dem Schritt 3 unten (`--commit`-Flag)
>   funktionsfähig ist, **muss** der Rest dieses Laufs ihn auch selbst
>   nutzen (dogfooding) — kein manuelles `git add` mehr für die
>   Ops-Commits dieses Laufs, siehe Schritt 6.

## Kontext

Bei BRIDGE-023 und BRIDGE-024 traten unabhängig voneinander zwei
Commit-Vollständigkeitsfehler auf:

1. **`result.yaml` → `changed_files` unvollständig** (beide Läufe): nur
   1–2 von tatsächlich 5+ geänderten Dateien gelistet. Root-Cause
   identifiziert (nicht geraten): `importer.collect_git_info(root,
   base_head)` berechnet `changed_files` per `git diff
   base_head..HEAD`. Der CLI-Parameter `--base-head` bei `bridge run
   finish` ist **optional** (`cli.py` Zeile 164, kein `required=True`,
   kein Default aus `task.yaml`). Fehlt er, fällt `collect_git_info`
   still auf `git diff-tree --no-commit-id --name-only -r HEAD` zurück —
   das zeigt **nur den letzten einzelnen Commit**, nicht den ganzen
   Lauf seit Taskerstellung. Kein Fehler, keine Warnung — stiller,
   falscher Erfolg.
2. **`task.yaml` fehlte im `run-finish`-Commit** (BRIDGE-0024, per
   Steuerchat-Nachtrag `ca4652b` behoben): Claude Code hat nach `bridge
   run finish` manuell `git add <Dateien>` ausgeführt und dabei eine
   tatsächlich geänderte Datei übersehen. Die in BRIDGE-024 gebaute
   Whitelist-Logik (`_git_commit_and_push`/`_expected_git_files`/
   `_matches_whitelist` in `src/bridge/webui.py`) löst genau dieses
   Problem bereits für die Web-UI — sie fehlt nur noch für die CLI, die
   Claude Code für die eigene Entwicklungsarbeit nutzt.

**Bewusst nicht im Scope:** Die CLI committet mit `--commit` **nur
lokal**, sie pusht nicht automatisch (anders als die Web-UI in
BRIDGE-024) — Push bleibt laut `CLAUDE.md` Regel 4 grundsätzlich
Mensch-/`GIT_PUSH`-Berechtigungssache, das ändert dieser Auftrag nicht.

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0025.yaml
   bridge run start BRIDGE-0025 --actor claude-code
   ```

2. **`src/bridge/gitops.py` neu anlegen** — Extraktion aus
   `webui.py` ohne Verhaltensänderung:
   - `_expected_git_files`, `_matches_whitelist`, `_git_commit_and_push`
     aus `webui.py` hierher verschieben (Funktionsnamen können ohne
     führenden Unterstrich werden, da jetzt öffentliches Modul-API:
     `expected_git_files`, `matches_whitelist`, `git_commit`).
   - `git_commit(...)` unterscheidet sich von der bisherigen
     `_git_commit_and_push` **nur** darin, dass Push **optional** wird
     (Parameter `push: bool = True`) — die Web-UI ruft weiterhin mit
     `push=True` (unverändertes Verhalten, bestehende
     `WebUiGitActionTests` müssen unverändert grün bleiben), die CLI
     ruft mit `push=False`.
   - `_expected_git_files`/`expected_git_files` um die für die CLI
     relevanten `kind`-Werte erweitern: `task_create`, `run_start`,
     `run_finish`, `task_copied`, `task_archive` — jeweils die Pfade,
     die die entsprechende Store-Funktion tatsächlich schreibt (im
     Funktionscode nachsehen, nicht raten — `store.py`/`runner.py`
     lesen).
   - `webui.py` importiert und nutzt `gitops.py` statt eigener
     Kopie — kein Parallel-Code.

3. **`--commit`-Flag zu den relevanten CLI-Subcommands hinzufügen**
   (`task create`, `run start`, `run finish`/`result import`, `task
   copied`, `task archive`):
   - Nach erfolgreicher Store-Aktion, falls `--commit` gesetzt:
     `gitops.git_commit(root, kind, task_id, actor, push=False)`
     aufrufen.
   - Erfolgsausgabe erweitern um die Commit-SHA; bei Whitelist- oder
     Branch-Fehler: **nicht stillschweigend weitermachen** — Exit-Code
     `3` (neu, in `--help` und `CLAUDE.md` dokumentieren) und
     Klartext-Fehler auf stderr, während die Store-Aktion selbst
     (bereits erfolgreich) nicht zurückgerollt wird — gleiche
     Trennung von Store-Erfolg/Git-Fehler wie in der Web-UI (BRIDGE-024).

4. **`base_head`-Fallback fail-closed statt still** (`importer.py`
   `collect_git_info`, aufgerufen aus `_cmd_result_import`/
   `run finish`):
   - Ist `--base-head` nicht gesetzt: **automatisch aus
     `task.yaml` → `git.expected_head` ableiten** (Feld existiert
     bereits im Schema, siehe eigene Staging-YAMLs als Referenz).
   - Ist auch `git.expected_head` nicht vorhanden: **fail-closed**,
     klare Fehlermeldung statt stillem Fallback auf „nur letzter
     Commit" (analog `SECURITY-MODEL.md` Abschnitt 4 — kein
     Improvisieren bei fehlender Ausgangslage).
   - Regressionstest, der exakt das BRIDGE-023/024-Szenario
     nachstellt: mehrere Commits seit Taskerstellung, `run finish`
     **ohne** `--base-head` → `changed_files` muss trotzdem den
     **gesamten** Lauf abdecken, nicht nur den letzten Commit.

5. Tests (`tests/test_gitops.py` neu, `tests/test_cli.py`/bestehende
   CLI-Tests erweitern):
   - `gitops.py`: Whitelist-Erfolg/-Fehlschlag pro `kind`, Branch-Check,
     kein `--force` (grep-bar), `push=False` committet lokal ohne
     Remote-Zugriff.
   - CLI-Integrationstest: `--commit` auf jedem der 5 Subcommands
     erzeugt genau einen Commit mit genau den erwarteten Dateien
     (per `git log`/`git show --stat` verifiziert, nicht nur
     Exit-Code).
   - `base_head`-Regressionstest wie in Schritt 4 beschrieben.
   - Bestehende `WebUiGitActionTests` unverändert grün (Regressionsschutz
     für die Extraktion).
   - Alle bestehenden Tests (`WebUiReadTests`, `WebUiActionTests`,
     `WebUiCliTests`, `WebUiFrontendTests`) weiterhin grün.

6. **Ab hier dogfooding** (siehe verbindlicher Hinweis oben): Für den
   Rest dieses Laufs `--commit` statt manuellem `git add` bei jedem
   weiteren `bridge`-Aufruf nutzen, der Store-Dateien ändert.

7. `docs/security/SECURITY-MODEL.md` und `CCB-STEUERCHAT-ARBEITSWEISE.md`
   (`docs/CCB-STEUERCHAT-ARBEITSWEISE.md`) um den neuen `--commit`-Flag
   und den `base_head`-Fail-closed-Mechanismus ergänzen — beide sollen
   künftig als Standardweg für Ops-Commits gelten, nicht nur als
   Option.

8. Pflicht-Footer + Abschluss:
   ```
   bridge run finish BRIDGE-0025 --status COMPLETED --actor claude-code \
     --commit \
     --summary "CLI haertet Commits: gitops.py als gemeinsames Modul (Web-UI + CLI), --commit-Flag auf 5 Subcommands (lokal, kein Push), base_head wird bei fehlendem Flag automatisch aus task.yaml.git.expected_head abgeleitet statt still auf letzten Commit zu degradieren (fail-closed sonst). Behebt die changed_files- und fehlende-Datei-Bugs aus BRIDGE-023/024."
   git push
   ```
   `Auftrag: BRIDGE-0025 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [x] `src/bridge/gitops.py` existiert, `webui.py` nutzt es (kein
      Parallel-Code, bestehende `WebUiGitActionTests` unverändert grün).
- [x] `--commit`-Flag auf `task create`, `run start`, `run finish`,
      `task copied`, `task archive` — committet lokal (kein Push),
      exakt die Whitelist-Dateien pro `kind`.
- [x] `--force`/`--force-with-lease` kommt im gesamten neuen/geänderten
      Code nicht vor (grep-bar).
- [x] Fehlt `--base-head` bei `run finish`, wird `git.expected_head` aus
      `task.yaml` automatisch verwendet; fehlt auch das, fail-closed
      statt stillem Fallback.
- [x] Regressionstest stellt das BRIDGE-023/024-Szenario nach:
      `changed_files` deckt bei fehlendem `--base-head` trotzdem den
      **gesamten** Lauf ab.
- [x] Whitelist-Fehler bei `--commit` führt zu Exit-Code `3` und
      Klartext-Fehler, Store-Aktion bleibt bestehen (kein Rollback).
- [x] `SECURITY-MODEL.md` und `CCB-STEUERCHAT-ARBEITSWEISE.md` um die
      neuen Mechanismen ergänzt.
- [x] Bestehende Tests (alle `WebUi*Tests`) weiterhin grün.
- [x] Neue Tests (`gitops`, CLI `--commit`, `base_head`-Regression)
      grün.
- [x] Alle Tests grün (bestehende Basis + neue), 246 Tests OK.
- [x] Ab Schritt 6 im eigenen Lauf: `--commit` statt manuellem
      `git add` genutzt (Commit bd5cd34, run_finish mit genau den erwarteten Dateien).
- [ ] Commit gepusht (dieser Auftrag trägt `GIT_PUSH`).
