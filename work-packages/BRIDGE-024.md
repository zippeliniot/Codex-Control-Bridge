# BRIDGE-024 — Web-UI: Aktionen selbst committen und pushen

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0024 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-0023 (ARCHIVED) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe HOCH — dies ist die erste Erweiterung der Web-UI um echte Git-Schreibrechte (bisher reine Store-/Runner-Logik ohne `subprocess`). Sicherheitsrelevant, siehe Abschnitt „Sicherheitsentscheid" unten. |

> **Verbindlich für diesen und jeden CCB-Auftrag:**
> - Jede Zustandsänderung läuft über die Bridge-CLI
>   (`bridge task create` / `bridge run start` / `bridge run beat` /
>   `bridge run finish`) — niemals direktes Bearbeiten von Dateien im
>   Store, um einen Status zu simulieren.
> - Dieser Auftrag trägt `GIT_PUSH` im Berechtigungsprofil. Nach
>   `run finish` **muss** `git push` ausgeführt werden — ohne Push kann
>   der Steuerchat das Ergebnis nicht per frischem Klon abrufen und
>   verifizieren (Regel 6 der Übergabe).

## Kontext

Bei BRIDGE-0023 hat sich in der Praxis gezeigt: Nach jeder Steuerchat-Aktion
über die Web-UI (`copied`, `archive`, `finish`) bleibt die Änderung nur lokal
in `task.yaml`/`audit.jsonl` — der Nutzer musste danach manuell in PowerShell
`git add`/`commit`/`push` ausführen, jedes Mal mit Rückfrage beim Steuerchat.
Das ist der bisher dokumentierte, bewusste Zustand (`SECURITY-MODEL.md`
Abschnitt 5a: „Kein Parallel-Code, kein eigener Audit-Pfad" bezog sich nur
auf die Store-Logik, nicht auf Git).

**Nutzerentscheidung (bestätigt):** Die Web-UI soll `git commit` **und**
`git push` nach jeder erfolgreichen Aktion selbst ausführen. Zusätzliche
Absicherung über die bereits vorhandene Bestätigungspflicht
(`confirm`+`actor`+Same-Origin-Prüfung) hinaus ist **nicht** gewünscht — kein
separates Freigabewort/Token.

## Sicherheitsentscheid (bewusst getroffen, hier dokumentiert)

Dies ist eine neue Fähigkeitsklasse für die Web-UI: bisher rein
dateibasierte Store-Operationen, jetzt zusätzlich `git commit`/`git push`
als Subprozess. `SECURITY-MODEL.md` Abschnitt 5a muss entsprechend erweitert
werden (siehe Schritt 5 unten) — nicht nur der Code.

Festgelegte Leitplanken, die **nicht verhandelbar** sind, unabhängig von der
obigen Nutzerentscheidung:

- **`--force` ist und bleibt in jedem Fall verboten** — auch hier, wie
  überall sonst im Projekt. Hart im Code verankert, nicht konfigurierbar.
- **Nur `main`, nur dieses Repo.** Branch wird vor jedem Commit per
  `git rev-parse --abbrev-ref HEAD` geprüft; weicht sie von `main` ab,
  Abbruch (fail-closed, analog Abschnitt 4 SECURITY-MODEL.md).
- **Kein `git add -A`.** Es wird ausschließlich die konkrete, pro Aktion
  bekannte Dateiliste gestaged (analog Übergabe-Regel 3). Zeigt
  `git status --porcelain` **irgendetwas außerhalb** dieser erwarteten Liste
  als geändert (z. B. weil parallel ein Claude-Code-Lauf etwas anderes
  angefasst hat), wird **nicht** committet — HTTP 409 mit Klartext-Fehler,
  Zustand bleibt unangetastet.
- **Kein automatisches Konfliktlösen.** Schlägt `git push` fehl (z. B.
  non-fast-forward, weil `origin/main` inzwischen weiter ist), wird das
  as-is an die UI zurückgemeldet (Commit ist ggf. bereits lokal vorhanden,
  Push nicht) — kein automatisches `pull --rebase`, kein `--force`, keine
  Wiederholung. Der Nutzer/Steuerchat löst das manuell auf.

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0024.yaml
   bridge run start BRIDGE-0024 --actor claude-code
   ```

2. **Dateiwhitelist pro Aktion definieren** (`src/bridge/webui.py`, neue
   Konstante/Funktion, z. B. `_expected_git_files(kind, task_id) -> list[str]`):
   - `copied`/`archive`: `tasks/<task_id>/task.yaml`, `audit/audit.jsonl`
   - `finish`: zusätzlich alles unter `results/<task_id>/<run_id>/` (bereits
     durch `runner.finish()`-Rückgabewert `result["run_id"]` bekannt) sowie
     ggf. `work-packages/<...>.md`, falls in diesem Lauf Checkboxen darin
     aktualisiert wurden — **nicht** raten, sondern die tatsächlich von
     `runner.finish()` erzeugten/geänderten Pfade zugrunde legen (im
     Funktionscode nachsehen, nicht annehmen).

3. **`_git_commit_and_push(repo_root, kind, task_id, actor)` implementieren**
   (neue Funktion in `src/bridge/webui.py`, `subprocess`-Import ergänzen):
   - `git status --porcelain` ausführen, Ergebnis gegen die Whitelist aus
     Schritt 2 abgleichen. Bei Abweichung: Abbruch, `_BadRequest`-artiger
     Fehler mit den unerwarteten Pfaden im Klartext, **kein** `git add`.
   - `git rev-parse --abbrev-ref HEAD` prüfen, muss `main` sein — sonst
     Abbruch mit Klartext-Fehler.
   - `git add <genau die Whitelist-Pfade>` (niemals `-A`).
   - `git commit -m "Ops: <task_id> <kind> (Steuerchat-Aktion via Web-UI)"`.
   - `git push` — **niemals** `--force` oder `--force-with-lease`.
   - Jeder `subprocess`-Aufruf mit Timeout, Rückgabecode und stderr/stdout
     einzeln geprüft; ein Fehlschlag bricht sofort ab und wird 1:1
     zurückgegeben, nicht generisch als „Fehler" verschluckt.

4. **`_apply_action` erweitern**: nach erfolgreichem
   `task_copied`/`task_archive`/`runner.finish` zusätzlich
   `_git_commit_and_push(...)` aufrufen. Response-JSON um ein `git`-Objekt
   erweitern: `{"committed": bool, "commit": "<sha-kurz>"|null, "pushed":
   bool, "error": "<text>"|null}`. Schlägt der Git-Teil fehl, bleibt die
   Store-Aktion selbst (bereits erfolgreich) bestehen — die Antwort meldet
   beides getrennt (Store-Erfolg **und** Git-Fehler gleichzeitig möglich),
   verschleiert nichts.

5. **Frontend** (`_PAGE`-Template, `post()`/`addLog()` aus BRIDGE-023):
   Log-Eintrag um Git-Ergebnis ergänzen — z. B. `→ committed a1b2c3d,
   gepusht` oder `→ committed a1b2c3d, Push fehlgeschlagen: <Kurzfehler>`.
   Kein neues UI-Element nötig, der bestehende persistente Log aus
   BRIDGE-023 reicht als Anzeigeort.

6. **`docs/security/SECURITY-MODEL.md` Abschnitt 5a erweitern** (nicht nur
   Code, auch Doku) — neuer Unterpunkt, der beschreibt:
   - dass die Web-UI jetzt Commit+Push selbst ausführt,
   - die Whitelist-Prüfung als Fail-closed-Mechanismus,
   - dass `--force` weiterhin kategorisch ausgeschlossen ist,
   - dass dies bewusst ohne zusätzliches Freigabewort erfolgt (Nutzerentscheidung,
     hier referenzieren), abgesichert allein über die bestehende
     `confirm`+`actor`+Same-Origin-Pflicht.

7. Tests (`tests/test_webui.py`, neue Klasse `WebUiGitActionTests`):
   - Testaufbau mit echtem temporären Git-Repo (statt nur Store-Temp-Dir wie
     bisher) **und** einem lokalen bare Repo als Test-„origin" (kein
     echter Netzwerkzugriff, kein `github.com` in Tests).
   - Erfolgsfall: Aktion committet genau die erwarteten Dateien, ein
     Commit, danach im bare-Repo per `git log` sichtbar (also wirklich
     gepusht).
   - Fail-closed-Fall: eine zusätzliche, nicht in der Whitelist stehende
     geänderte Datei im Arbeitsverzeichnis → Aktion schlägt mit 409/Fehler
     fehl, **kein** Commit entsteht (per `git log` im Test-Repo verifizieren,
     nicht nur den HTTP-Status).
   - Push-Fehlschlag simulieren (z. B. bare-Repo vorher divergieren lassen)
     → Commit bleibt lokal, `pushed: false`, Fehlertext vorhanden, kein
     Crash, kein automatischer Retry.
   - Bestehende Tests (`WebUiReadTests`, `WebUiActionTests`,
     `WebUiCliTests`, `WebUiFrontendTests` aus BRIDGE-023) bleiben grün.

8. Pflicht-Footer + Abschluss:
   ```
   bridge run finish BRIDGE-0024 --status COMPLETED --actor claude-code \
     --summary "Web-UI fuehrt nach copied/archive/finish jetzt selbst git commit + git push aus, abgesichert durch Datei-Whitelist-Check (fail-closed bei unerwarteten Aenderungen), Branch-main-Pruefung und kategorischem force-push-Verbot. SECURITY-MODEL.md Abschnitt 5a entsprechend erweitert."
   git push
   ```
   `Auftrag: BRIDGE-0024 / Lauf: RUN-01 / Status: COMPLETED`

   **Wichtig:** dieser letzte `git push` (für den eigenen Code-/Doku-Commit
   von BRIDGE-024) läuft noch über den bisherigen manuellen Weg — die neue
   Selbst-Push-Fähigkeit der Web-UI gilt nur für die drei Aktions-Endpunkte
   (`copied`/`archive`/`finish`), nicht für Claude Codes eigene
   Entwicklungs-Commits.

## Akzeptanzkriterien

- [x] `git status --porcelain` wird vor jedem Commit gegen eine feste
      Datei-Whitelist pro Aktionstyp geprüft; unerwartete Änderungen blocken
      den Commit vollständig (kein Teil-Commit).
- [x] Branch-Prüfung: Commit/Push nur auf `main`, sonst Abbruch mit
      Klartext-Fehler.
- [x] `--force`/`--force-with-lease` kommt im gesamten neuen Code nicht vor
      (grep-bar, kein bedingter Pfad, der es aktivieren könnte).
- [x] Erfolgreiche Aktion erzeugt genau einen Commit mit genau den
      erwarteten Dateien und pusht ihn (im Test gegen ein lokales bare
      Repo verifiziert, kein echter `github.com`-Zugriff in Tests).
- [x] Push-Fehlschlag wird transparent gemeldet (`pushed: false` +
      Fehlertext), ohne Crash, ohne automatischen Retry, ohne `--force`.
- [x] Store-Erfolg und Git-Fehler werden getrennt und wahrheitsgemäß
      gemeldet (kein „alles ok", wenn nur der Store-Teil geklappt hat).
- [x] Persistenter Aktions-Log (BRIDGE-023) zeigt das Git-Ergebnis pro
      Eintrag.
- [x] `SECURITY-MODEL.md` Abschnitt 5b (neu, nach 5a) um die neue Fähigkeit,
      die Whitelist-Prüfung und das Force-Push-Verbot erweitert.
- [x] Bestehende Tests (`WebUiReadTests`, `WebUiActionTests`,
      `WebUiCliTests`, `WebUiFrontendTests`) weiterhin grün.
- [x] Neue Tests (`WebUiGitActionTests`) grün, inkl. Fail-closed- und
      Push-Fehlschlag-Fall.
- [x] Alle Tests grün (bestehende Basis + neue), frischer Klon verifiziert.
- [x] Commit gepusht (dieser Auftrag trägt `GIT_PUSH`).
