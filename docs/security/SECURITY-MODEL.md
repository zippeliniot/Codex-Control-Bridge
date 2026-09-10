# Sicherheitsmodell — Codex Control Bridge

> **Status:** verbindlich ab BRIDGE-001.

## 1. Grundsatz: Least Privilege

Die Bridge erhält **niemals allein aufgrund eines eingegangenen Auftrags**
unbeschränkte Rechte. Jeder Auftrag trägt ein explizites Berechtigungsprofil.

**Default:**

```
READ_ONLY
```

Erweiterte Rechte müssen ausdrücklich im Auftrag vorhanden sein.

## 2. Rechtestufen

```
READ_ONLY
WORKTREE_WRITE
TEST_EXECUTION
GIT_STAGE
GIT_COMMIT
GIT_PUSH
PR_CREATE
MERGE
DEPLOY
DATABASE_WRITE
```

## 3. Kritische Aktionen — nie implizit

Die folgenden Aktionen dürfen **nur** bei ausdrücklicher, auftragsgebundener
Freigabe erfolgen und niemals aus einer schwächeren Stufe abgeleitet werden:

```
MERGE
DEPLOY
DATABASE_WRITE
FORCE_PUSH
MIGRATION_PRODUCTION
```

## 4. Fail-closed

Bei jeder der folgenden Situationen wird der Auftrag `BLOCKED` — die Bridge
improvisiert nicht:

- falscher Worktree
- unerwarteter HEAD
- unbekannter Auftrag
- Ergebnis für falsche Task-ID
- unerlaubte Git-Aktion
- nicht eindeutige Maschinenidentität
- beschädigte Task-Datei
- Schemafehler

## 5. Git-Sicherheit

Der Git-Zustand ist Teil der Auftragsidentität. Vor einem Lauf mindestens:

```
repository · branch · HEAD · upstream · ahead/behind · worktree status · index status
```

Bei relevanten Aufträgen zusätzlich:

```
expected_head · allowed_changed_files · expected_diff_hash
```

Stimmt die erwartete Ausgangslage nicht, bricht der Auftrag ab (fail-closed).

## 5a. Web-UI (BRIDGE-020)

Die lokale Web-UI (`bridge webui serve`) ist eine dünne Anzeige- und
Bedienschicht über den bereits abgesicherten Store-/Runner-Funktionen.

- **Bindung ausschließlich an `127.0.0.1`.** Kein `0.0.0.0`, keine
  `--host`-Option — die Adresse ist im Code hart verdrahtet
  (`webui.HOST`). Das ist die technische Umsetzung von „keine externe
  Erreichbarkeit", nicht nur eine Empfehlung: ein Aufweichen der Bindung
  würde die ungeschützte Bridge-Steuerung für das gesamte Netz öffnen.
- **Kein Auth-Layer.** Bewusst, weil der Dienst nur lokal auf einer
  Ein-Nutzer-Maschine erreichbar ist. Diese Lücke ist hier ausdrücklich
  dokumentiert, damit niemand später `--host 0.0.0.0` ergänzt, ohne das
  fehlende Login zu bedenken.
- **Lesend** (`GET /`, `GET /api/board`): jede unbekannte Route/Methode
  antwortet 404/405. Ein Store-/Profilfehler wird als JSON-Fehlerobjekt
  mit HTTP 500 zurückgegeben und beendet den Server nicht.
- **Schreibende Aktions-Endpunkte** (`POST /api/task/<id>/copied`,
  `POST /api/task/<id>/archive`, `POST /api/run/<id>/finish`) rufen
  dieselbe Store-/Runner-Logik wie die entsprechenden CLI-Kommandos auf
  (kein Parallel-Code, kein eigener Audit-Pfad). Zusätzlich abgesichert:
  - **Serverseitige Bestätigungspflicht:** ohne `confirm: true` und ohne
    nicht-leeren `actor` → HTTP 400. Der Browser-Dialog ist nur UX; ein
    `curl`-Aufruf ohne `confirm` löst nichts aus.
  - `run finish` zusätzlich: ohne nicht-leere `summary` → HTTP 400
    (setzt die `--summary`-Pflicht aus `CLAUDE.md` / BRIDGE-021 durch).
  - **Same-Origin-Prüfung:** `Origin` (ersatzweise `Referer`) jedes
    `POST` muss `http://127.0.0.1:<port>` sein, sonst HTTP 403 — Schutz
    gegen einen fremden Browser-Tab, der im Hintergrund gegen `localhost`
    postet. Kein CSRF-Token (Single-User, kein Login), aber nicht
    optional.
  - Eine im aktuellen Zustand unzulässige Aktion wird mit HTTP 409 und
    derselben Fehlermeldung wie im CLI abgelehnt (nicht stillschweigend
    ignoriert).

### 5b. Web-UI: Git-Commit und Push nach Aktionen (BRIDGE-024)

Ab BRIDGE-024 führt die Web-UI nach jeder erfolgreichen Aktion
(`copied`, `archive`, `finish`) automatisch `git commit` und `git push`
aus. Dies ist eine neue Fähigkeitsklasse für die Web-UI (bisher nur
dateibasierte Store-Operationen, jetzt zusätzlich Subprozesse). Die
folgende Entscheidung ist bewusst getroffen und hier dokumentiert.

**Nutzerentscheidung (bestätigt):** Kein zusätzliches Freigabewort/Token
über die bestehende `confirm`+`actor`+Same-Origin-Pflicht hinaus. Die
bereits vorhandene dreifache Absicherung wird als ausreichend bewertet.

**Nicht verhandelbare Leitplanken:**

- **`--force` und `--force-with-lease` sind kategorisch verboten** — auch
  hier, wie überall sonst im Projekt. Hart im Code verankert
  (`_git_commit_and_push` in `webui.py`), kein konfigurierter Pfad, der
  es aktivieren könnte (grep-bar verifizierbar).
- **Branch-Prüfung:** Vor jedem Commit prüft `git rev-parse
  --abbrev-ref HEAD`; weicht der Branch von `main` ab, bricht die
  Funktion mit Klartext-Fehler ab (fail-closed, analog Abschnitt 4).
- **Datei-Whitelist (fail-closed):** Es wird niemals `git add -A`
  verwendet. Stattdessen gibt `_expected_git_files(kind, task_id, run_id)`
  für jede Aktion die erlaubten Pfade zurück:
  - `copied`/`archive`: `tasks/<id>/task.yaml`, `audit/audit.jsonl`
  - `finish`: zusätzlich alles unter `results/<id>/<run_id>/` und
    `work-packages/<id>.md`

  Zeigt `git status --porcelain` irgendetwas außerhalb dieser Liste, wird
  **kein** `git add` ausgeführt und der Commit wird abgebrochen — kein
  Teil-Commit, keine stille Ignorierung.

- **Kein automatisches Konfliktlösen:** Schlägt `git push` fehl (z. B.
  non-fast-forward), wird der Fehler 1:1 an die UI zurückgemeldet
  (`pushed: false` + Klartext). Kein automatisches `pull --rebase`, kein
  `--force`, keine Wiederholung.

- **Store-Erfolg und Git-Fehler werden getrennt gemeldet:** Schlägt der
  Git-Teil fehl, bleibt die Store-Aktion (bereits erfolgreich) bestehen.
  Die Antwort enthält immer ein `git`-Objekt
  (`committed`, `commit`, `pushed`, `error`). Kein „alles ok", wenn nur
  der Store-Teil geklappt hat.

### 5c. CLI: --commit-Flag und base_head-Fail-closed (BRIDGE-025)

Ab BRIDGE-025 kann die CLI nach einer erfolgreichen Store-Aktion optional
lokal committen. Im Unterschied zur Web-UI (Abschnitt 5b) pusht die CLI
**nicht** automatisch — Push bleibt laut `CLAUDE.md` Regel 4 grundsätzlich
Mensch-/`GIT_PUSH`-Berechtigungssache.

**`--commit`-Flag:** Vorhanden auf `task create`, `run start`, `run finish`,
`task copied`, `task archive`. Nach erfolgreicher Store-Aktion werden
ausschließlich die von der Store-Funktion tatsächlich geschriebenen Dateien
per `gitops.git_commit(push=False)` committet. Dieselben Sicherheitsleitplanken
wie in 5b gelten unverändert (Branch `main`, Datei-Whitelist fail-closed, kein
Force-Push, kein `git add -A`). Bei Whitelist- oder Branch-Fehler: **Exit-Code 3**,
Klartext-Fehler auf stderr — die Store-Aktion (bereits erfolgreich) wird nicht
zurückgerollt.

**Gemeinsames Modul `gitops.py`:** Die Whitelist-Logik lebt jetzt in
`src/bridge/gitops.py` (Funktionen `expected_git_files`, `matches_whitelist`,
`git_commit`). Web-UI und CLI teilen sich diese Implementierung — kein
Parallel-Code.

**`base_head` fail-closed (fix für BRIDGE-023/024-Bug):** Bei `run finish`
und `result import` war `--base-head` bisher optional mit stillem Fallback
auf `git diff-tree HEAD` (nur letzter Commit). Ab BRIDGE-025:

1. Fehlt `--base-head`: wird `git.expected_head` aus `task.yaml` automatisch
   verwendet (der SHA zum Zeitpunkt der Taskerstellung).
2. Fehlt auch `git.expected_head`: **fail-closed** (Exit-Code 1, Klartext-Fehler),
   kein stiller Fallback — analoog Abschnitt 4.

Damit ist `changed_files` in `result.yaml` garantiert vollständig (alle Commits
seit Taskerstellung, nicht nur der letzte).

## 6. Grenzen der ersten Version (Nicht-Ziele)

Zunächst ausdrücklich **nicht** vorgesehen:

- selbstständige fachliche Projektentscheidungen
- automatische Freigabe kritischer Git-Aktionen
- automatisches Merge in `main`
- autonomes Deployment
- produktive Datenbankänderungen
- automatische Architektur- oder Sicherheitsfreigaben
- unkontrollierter Zugriff auf beliebige Repositories
- direkte Manipulation laufender Chats ohne vorgesehene Schnittstelle
