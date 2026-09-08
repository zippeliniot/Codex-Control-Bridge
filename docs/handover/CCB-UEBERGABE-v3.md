# Codex Control Bridge (CCB) — Übergabe an neuen Chat (Stand nach BRIDGE-021)

Dieses Dokument fasst Projekt, Stand und offene nächste Schritte zusammen,
damit ein neuer Chat nahtlos weiterarbeiten kann. Löst die vorherige
Übergabe (CCB-UEBERGABE-v2.md, Stand nach BRIDGE-018) ab.

---

## 0. Verbindliche Arbeitsanweisungen für diesen Chat (zuerst lesen)

Seit der letzten Übergabe sind mehrere vermeidbare Fehler passiert, jeweils
mit Ursache dokumentiert. Diese Regeln gelten ab der ersten Nachricht:

1. **Vor dem allerersten Commit/ZIP in diesem Chat:** den Nutzer erst
   `git fetch origin` + `git log --oneline origin/main -5` gegen den
   lokalen Stand prüfen lassen — NICHT annehmen, dass der lokale Klon
   aktuell ist.

2. **Windows-CLI-Aufruf: `python src\bridge\cli.py --root . --schema-dir
   schemas <kommando>`, NIEMALS `-m bridge.cli`.** *(Ursache, sehr teuer:
   `-m bridge.cli` scheitert ohne gesetztes `PYTHONPATH` mit
   `ModuleNotFoundError: No module named 'bridge'`. Bei BRIDGE-019 wurde
   dieser Fehler nicht bemerkt — der Nutzer hat trotzdem `git add -A &&
   git commit && git push` ausgeführt, was zufällig unstaged Änderungen
   eines ANDEREN Auftrags mitgenommen hat und wie ein Erfolg aussah. Der
   eigentliche `task copied`/`task archive`-Aufruf lief nie. Das ist erst
   drei Chatrunden später über den Audit-Trail aufgefallen. `PYTHONPATH=src
   python -m bridge` funktioniert als Alternative, ist aber fehleranfälliger
   für den Nutzer — die `src\bridge\cli.py`-Form ist Standard, siehe
   README.md Zeile 119.)*

3. **Nach jedem Bridge-CLI-Befehl, der einen Zustand ändert (`task copied`,
   `task archive`, `run finish`, …): die tatsächliche Ausgabe ansehen, nicht
   nur "ok"/"fertig" vom Nutzer akzeptieren.** Bei Zweifel: `git log
   --oneline -5` UND `grep <BRIDGE-id> audit/audit.jsonl` verlangen, nicht
   nur eine der beiden. Eine Commit-Message ist keine verlässliche Quelle
   für das, was tatsächlich passiert ist (siehe Punkt 2 und Punkt 5).

4. **Nach `git fetch`: die Arbeitskopie mit `git reset --hard origin/main`
   (oder einem frischen Klon) aktualisieren, bevor Board/Tests/Dateien
   geprüft werden.** *(Ursache: `git fetch` aktualisiert nur Referenzen,
   nicht die Arbeitskopie — ein Review direkt danach zeigte veraltete
   Board-Daten, obwohl `origin/main` schon weiter war.)*

5. **Nie zwei Aufträge gleichzeitig unstaged im selben Arbeitsverzeichnis
   offen lassen.** Wenn Auftrag A abgeschlossen wird, während Auftrag B noch
   in Bearbeitung ist: gezielt die eigenen Pfade von A stagen (`git add
   <pfade>`), nicht `git add -A`. *(Ursache: Bei BRIDGE-019/BRIDGE-021 lief
   `git add -A` für den Abschluss von BRIDGE-019, während Claude Code
   BRIDGE-021 mitten in der Bearbeitung hatte — `CLAUDE.md` aus BRIDGE-021
   landete dadurch fälschlich im BRIDGE-019-Commit. Musste per
   Klarstellungs-Commit nachträglich richtiggestellt werden.)*

6. **Bridge-CLI-Befehle für den Nutzer immer mit `.venv\Scripts\python.exe
   src\bridge\cli.py --root . --schema-dir schemas ...`.**

7. **ZIP-Dateien landen beim Nutzer im Download-Verzeichnis**
   (`$env:USERPROFILE\Downloads\...`), NICHT im Projektverzeichnis.

8. **Task-Spezifikationen für `bridge task create` immer unter
   `tasks/incoming/BRIDGE-xxxx.yaml`**, NIE direkt am kanonischen
   Store-Pfad. Nach erfolgreichem `task create` die Staging-Datei löschen.

9. **Jeder Befehl an den Nutzer:** als kopierfertiger Codeblock, mit
   vorangestelltem `**WO:**`.

10. **Vor jedem Claude-Code-Auftrag:** Modell UND Denkstufe explizit
    nennen. Sonnet ist Standard, Opus nur bei echtem Architektur-Neuland.

11. **Nach jedem Push:** selbst frisch von `origin/main` klonen (oder
    `reset --hard`, siehe Punkt 4), Testsuite laufen lassen, Diff gegen die
    Akzeptanzkriterien der Spezifikation prüfen — nicht nur `result.yaml`
    vertrauen (siehe Punkt 12).

12. **`bridge run finish` MUSS mit `--summary "..."` aufgerufen werden**
    (seit BRIDGE-021 in `CLAUDE.md` verbindlich). Ein nackter Aufruf lässt
    `result.yaml` ohne `summary`/`acceptance_results` und mit unvollständigen
    `changed_files` zurück (entdeckt bei BRIDGE-019).

13. **Nach jedem abgeschlossenen, gepushten Paket:** `/clear` in Claude Code
    vorschlagen, bevor der nächste Auftrag kommt.

14. Bei echten Scope- oder Architekturfragen: kurz nachfragen, aber immer
    mit einer konkreten Empfehlung.

---

## 1. Was das Projekt ist

Die **Codex Control Bridge (CCB)** ist eine projektunabhängige Vermittlungsschicht
für strukturierte Aufträge/Ergebnisse zwischen einem **Steuerprozess** und einer
**Ausführungsinstanz**. GitHub ist die **einzige Quelle (SSOT)**.

- Repo (öffentlich): https://github.com/zippeliniot/Codex-Control-Bridge
- Fachliches Konzept: `docs/PROJEKTKONZEPT.md`

**Seit BRIDGE-019 real erreicht:** Die Bridge ist nicht mehr nur auf
"Claude im Browser + Claude Code" festgelegt. `executor`/`controller` können
jetzt pro Auftrag überschrieben werden (nicht mehr nur pro Projekt fest),
es gibt ein `review_roles`-Feldpaar (`lead`/`support`) für fachliche
Führungs-/Prüfrollen bei gegenseitiger Kontrolle, ein `github_repo`-Feld für
Steuerprozesse ohne lokalen Checkout (z. B. ChatGPT über einen
GitHub-Connector), und `CONTROL.md` als ChatGPT-Pendant zu `CLAUDE.md`.
**Wichtig:** Das ist reine Infrastruktur — es läuft aktuell **kein** echter
Codex-/ChatGPT-Livebetrieb. Das CCB-Projekt selbst bleibt
`executor: claude-code` / `controller: human`.

## 2. Rollenverteilung

- **Claude im Browser (Steuer-/Review-Ebene):** schreibt Spezifikationen als
  `work-packages/BRIDGE-xxxx.md` + `tasks/incoming/BRIDGE-xxxx.yaml`,
  reviewt den gepushten Stand gegen GitHub (frischer Klon/Reset, Tests,
  gezielte Diff-Prüfung gegen Akzeptanzkriterien). Kann NICHT pushen.
- **Claude Code (Ausführung, native Windows-App):** implementiert Code +
  Tests, führt Bridge-CLI-Befehle selbst aus, committet klein, pusht NICHT
  selbst (Push bleibt Mensch-Aktion).
- **ChatGPT (optionaler zweiter Steuerprozess, noch nicht aktiv):** siehe
  `CONTROL.md`. Hat GitHub-Lesezugriff über einen Connector verifiziert,
  Schreibrechte technisch verfügbar aber ungetestet/nicht freigegeben.
- **Codex (optionale zweite Ausführungsinstanz, noch nicht aktiv):** keine
  isolierte CCB-Umgebung vorhanden — nur aus Dorfschaft bekannt (HAM01/WSL),
  dieser Worktree ist für CCB tabu. Aktivierung braucht einen eigenen,
  getrennten Checkout/`.venv`/Git-Identität — noch nicht eingerichtet.
- **Mensch:** spielt Spezifikations-ZIPs ein, bestätigt Claude-Code-Aktionen,
  pusht, führt `task copied`/`task archive` aus, stößt den jeweils anderen
  Chat an.

## 3. Systemlandschaft (unverändert)

- Zwei physisch getrennte Windows-PCs: **HAM11** und **DES11**, Basis
  `E:\_DEV\Codex-Control-Bridge` (in `registry.yaml` versioniert).
- Claude Code läuft nativ unter Windows, nicht in WSL.
- Python-Arbeit immer im repo-lokalen `.venv`.
- **CLI-Aufruf:** `python src\bridge\cli.py --root . --schema-dir schemas
  <kommando>` (siehe Abschnitt 0, Punkt 2 — nicht `-m bridge.cli`).
- Aktuell wird auf **HAM11** gearbeitet.

## 4. Verbindliche Regeln (Guardrails)

- SSOT im Repo; Fail-closed bei jeder Unsicherheit.
- Least privilege: Bridge/Watcher/Runner führen NIE Git-Aktionen aus.
- `bridge_task_id`-Format: `<PRÄFIX max. 8 Großbuchstaben>-<4 Ziffern>`.
- Granulare Git-Rechte pro Auftrag über `permissions`:
  `READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION, GIT_STAGE, GIT_COMMIT,
  GIT_PUSH, PR_CREATE, MERGE, DEPLOY, DATABASE_WRITE, FORCE_PUSH` — Standard
  `[READ_ONLY]`. Ein Connector-gesteuerter Akteur (ChatGPT) bekommt den
  engstmöglichen Auszug, nie automatisch die volle Liste.
- **Neu (BRIDGE-019):** `executor`/`controller` in `project.yaml` sind
  Projekt-Defaults; `task.yaml` kann sie pro Auftrag überschreiben (`null`
  = vom Projekt erben). Gleiches Muster für `review_roles` (`lead`/
  `support`, komplett oder gar nicht — kein Teil-Mischen von Task-`lead`
  mit Projekt-`support`).
- **Neu (BRIDGE-019):** `github_repo` in `project.yaml` — vollqualifizierter
  `Besitzer/Repo`-Slug für Steuerprozesse ohne lokalen Checkout. Getrennt
  vom Feld `repository`, das nur der lokale Verzeichnisname ist.
- **Neu (BRIDGE-021):** `bridge run finish` MUSS `--summary` bekommen.
- `read_only: true` hart erzwungen (Allowlist).
- Pflicht-Footer am Ende jedes Claude-Code-Auftrags:
  `Auftrag: BRIDGE-xxxx / Lauf: RUN-yy / Status: ...`
- Checkpoint-&-Resume: kleine Commits, gezielt gestaged (siehe Abschnitt 0,
  Punkt 5 — kein `git add -A`, wenn ein anderer Auftrag parallel offen ist).
- Claude-Code-Auto-Modus AUS halten; vor jedem Auftrag Modell UND Denkstufe.
- `/clear` in Claude Code nach jedem abgeschlossenen, gepushten Paket.

## 5. Stand: fertig, reviewt, auf GitHub (BRIDGE-001 bis BRIDGE-021)

**BRIDGE-001 bis BRIDGE-018:** wie in der Vorgänger-Übergabe beschrieben,
unverändert gültig (Kernmodule, Schemas, Zustandsmodell, Store, CLI, Watcher,
Runner, Profile, Board, `board --watch`).

**BRIDGE-019 — Mehrfach-Steuerung (Task-Override, review_roles,
github_repo):** `executor`/`controller` jetzt pro Auftrag überschreibbar
(Resolutionslogik `resolve_executor`/`resolve_controller`/
`resolve_review_roles` in `src/bridge/profiles.py`, Muster wie
`model`/`reasoning_level`). Neues `review_roles`-Feldpaar (`lead`/`support`)
auf Projekt- und Task-Ebene. `bridge board` zeigt neue Spalte
„Führung/Prüfung" (`_board_review_roles` in `src/bridge/cli.py`, fail-soft
auf `"?"`). Neues `github_repo`-Feld in `project.yaml`, CCB-Profil bekommt
`github_repo: zippeliniot/Codex-Control-Bridge`. Neues `CONTROL.md`
(ChatGPT-Pendant zu `CLAUDE.md`), `CLAUDE.md` verweist darauf. Alle
Erweiterungen additiv/nullable — bestehende Profile/Tasks bleiben ohne
Änderung gültig. **Lernpunkt:** Der Abschluss (`task copied`/`task archive`)
schlug initial an `ModuleNotFoundError` still fehl, siehe Abschnitt 0,
Punkt 2 — musste nachträglich korrekt nachgeholt werden.

**BRIDGE-021 — `run finish --summary` verbindlich:** `CLAUDE.md` um
Unterabschnitt ergänzt, der `--summary` bei jedem `run finish`-Aufruf
vorschreibt. **Lernpunkt:** Die eigentliche Inhaltsänderung landete durch
gleichzeitige Arbeit an zwei Aufträgen im selben Arbeitsverzeichnis
versehentlich im BRIDGE-019-Abschluss-Commit (`0896d098`) statt in einem
eigenen BRIDGE-021-Commit — per Klarstellungs-Commit (`99d89e7`)
nachträglich richtiggestellt, keine inhaltliche Änderung nötig, siehe
Abschnitt 0, Punkt 5.

**Testsuite:** 173 Tests, grün bei frischem Klon (mehrfach verifiziert,
zuletzt gegen `16208c8`).

**Prüfen im neuen Chat:** letzten Commit-Stand von `origin/main` gegenlesen
(sollte bei `16208c8` oder später stehen), `bridge board` sollte leer sein
(BRIDGE-0019 und BRIDGE-0021 sind `ARCHIVED`, per Audit-Trail verifiziert,
nicht nur Commit-Message).

## 6. Wichtige technische Klarstellungen für den neuen Chat

- **Ein zentraler Store, keine Multi-Repo-Traversierung** (unverändert).
- **`tasks/incoming/` ist reines Staging** (unverändert).
- **Board zeigt nur zwei Zustände:** `WAITING_FOR_HANDOFF_TO_EXECUTOR` und
  `WAITING_FOR_COPY_TO_CONTROL` — laufende Arbeit (`CLAIMED`/`RUNNING`) ist
  bewusst nicht sichtbar. Board ist ein Dirigent, kein Fortschrittsmonitor.
- **Kein Lock-/Claim-Schutz gegen echte Parallelität.** Der Store ist reine
  Dateien in einem Git-Repo, keine Sperre gegen gleichzeitiges Bearbeiten
  desselben Auftrags durch zwei Akteure — Schutz aktuell nur durch klare
  Projekt-/Auftrags-Zuordnung von `executor`/`controller`, nicht technisch
  erzwungen. Offener Punkt für später (siehe Abschnitt 7).
- **`executor`/`controller`/`review_roles`-Auflösung:** Task-Wert gewinnt,
  wenn nicht `null`; sonst Projekt-Default; sonst `None`. Bei
  `review_roles` gilt der Task-Wert nur als Ganzes.
- **Aktuelle Auflösung nur Anzeige/Kennzeichnung, keine technische
  Durchsetzung.** Eine `support`-Rolle wird nicht daran gehindert, trotzdem
  zu pushen — bewusste Entscheidung (siehe Verlauf), erst im Alltag testen,
  Durchsetzung als möglicher Folgeschritt.

## 7. Offene Punkte / mögliche nächste Schritte

1. **BRIDGE-020 — Web-UI (Stufe 1 + Stufe 2), bereits besprochen, noch
   nicht spezifiziert:** lokales Lese-Board im Browser (`_board_rows()`
   wiederverwenden, dünner Webserver, Auto-Refresh) + Aktions-Buttons
   (`task copied`/`task archive`/`run finish`) mit Bestätigungslogik. Rein
   `localhost`, keine externe Erreichbarkeit. Intern zwei Schritte (erst
   Lese-Endpunkte, dann Aktions-Endpunkte), aber ein Auftrag. **Das ist der
   nächste geplante Schritt.**
2. **Codex-/ChatGPT-Aktivierung (noch keine Nummer vergeben):**
   Voraussetzung: eigener, von Dorfschaft getrennter Codex-Checkout/`.venv`/
   Git-Identität auf einer Maschine (physische Einrichtung durch April,
   kein Codeauftrag), danach ein eng begrenzter GitHub-Schreib-Canary-Test
   für ChatGPT (nur `tasks/incoming/`, mit Mensch live beobachtend). Erst
   danach `executor: codex`/`controller: openai` real testen. Nicht von
   selbst anfangen, aktiv ansprechen sobald April die Umgebung eingerichtet
   hat.
3. **Claim-/Lock-Schutz gegen echte Parallelität** (siehe Abschnitt 6):
   optimistischer Lock über den beim Lesen gesehenen commit-Hash, `run
   start` schlägt fail-closed fehl (→ `BLOCKED`), wenn der Auftrag
   zwischenzeitlich von woanders verändert wurde. Sinnvoll, sobald mehr als
   ein Controller/Executor-Paar gleichzeitig aktiv wird.
4. **`review_roles`-Durchsetzung** (nicht nur Anzeige) — zurückgestellt,
   bis sich im Alltag zeigt, dass reine Sichtbarkeit nicht reicht.
5. **Endbild** (dauerhafter manueller Dirigent vs. API-Vollautomatik, Stufe
   3) — Entscheidungsfrage an April, aktiv ansprechen sobald Punkt 2 einmal
   gelaufen ist.

## 8. Delivery-Konvention (unverändert)

Browser-Claude liefert pro Paket ein ZIP mit `work-packages/BRIDGE-xxxx.md`
+ `tasks/incoming/BRIDGE-xxxx.yaml` (Staging-Pfad!). Mensch: `git pull`
zuerst, dann `Expand-Archive ... -Force`, committen, pushen.

## 9. Erste Aktionen im neuen Chat (exakte Reihenfolge, nicht optional)

**Schritt 1 — Stand verifizieren, bevor irgendetwas anderes passiert:**

```bash
git clone --quiet https://github.com/zippeliniot/Codex-Control-Bridge.git ccb_check
cd ccb_check
git log --oneline -3
python3 -m venv .venv && .venv/bin/pip install -q pyyaml jsonschema
.venv/bin/python -m unittest discover -s tests
export PYTHONPATH="$(pwd)/src"
.venv/bin/python -m bridge.cli --root . --schema-dir schemas board
```

Erwartung: `HEAD` bei `16208c8` oder neuer, alle Tests grün (mind. 173),
`bridge board` gibt `(keine Auftraege warten auf Kopie)` aus. Weicht etwas
ab: NICHT weitermachen, sondern zuerst mit dem Nutzer klären.

**Schritt 2 — lokalen Stand des Nutzers gegenprüfen, bevor der erste eigene
Befehl an ihn geht:**

```powershell
git fetch origin
git log --oneline origin/main -3
git log --oneline HEAD -3
```

Stimmen beide `HEAD`-Zeilen überein → weiter. Weichen sie ab → erst klären.

**Schritt 3 — die Empfehlung aus Abschnitt 7, Punkt 1 aktiv vorschlagen**
(kein offenes "was jetzt?"): kurz zusammenfassen, dass Mehrfach-Steuerung
(BRIDGE-019) und die `--summary`-Pflicht (BRIDGE-021) stehen, und konkret
vorschlagen, jetzt die BRIDGE-020-Spezifikation (Web-UI Stufe 1+2) zu
schreiben — mit der Rückfrage, ob das passt oder ob stattdessen etwas
anderes ansteht.
