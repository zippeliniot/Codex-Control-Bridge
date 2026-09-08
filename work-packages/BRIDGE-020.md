# BRIDGE-020 — Web-UI Stufe 1 (Lese-Board) + Stufe 2 (Aktions-Buttons)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0020 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM (neue Schnittstellenschicht über bestehenden, bereits getesteten Store-/Runner-/Board-Funktionen — kein neues Architekturkonzept, keine neuen Zustände, keine neuen Schema-Felder. Vergleichbar mit BRIDGE-019, das ebenfalls MEDIUM war.) |

## Kontext

Aus Abschnitt 7, Punkt 1 der Übergabe: ein lokales Lese-Board im Browser
(`_board_rows()` wiederverwenden, dünner Webserver, Auto-Refresh) plus
Aktions-Buttons (`task copied`/`task archive`/`run finish`) mit
Bestätigungslogik. Rein `localhost`, keine externe Erreichbarkeit.

**Ein Auftrag, zwei Läufe — keine zwei BRIDGE-IDs.** Beide Stufen bauen auf
demselben neuen Modul und derselben CLI-Anbindung auf; eine Aufteilung in
zwei BRIDGE-IDs würde nur eine künstliche `depends_on`-Kette und doppelten
Review-Aufwand für dieselbe Codebasis erzeugen. Stattdessen wird das
ohnehin vorhandene Checkpoint-&-Resume-Muster genutzt (siehe `CLAUDE.md`):

- **RUN-01** liefert Stufe 1 (nur lesend) und schließt mit `run finish
  --status COMPLETED --summary "..."` ab. Danach `task copied` /
  `task archive` wie gewohnt durch den Menschen.
- **RUN-02** wird über `bridge run resume BRIDGE-0020 --actor claude-code`
  auf demselben Auftrag eröffnet und liefert Stufe 2 (Aktions-Buttons).
  Setzt lückenlos auf RUN-01 auf — kein neuer Auftrag, kein neues Review
  von Grund auf.

Das hält beide Stufen in einem nachvollziehbaren, aber dennoch klar
checkpointbaren Paket, statt eine zweite Bridge-ID nur wegen der internen
Reihenfolge zu erzeugen.

### Architekturentscheidung, die dieses Paket bereits trifft (nicht mehr offen)

`_board_rows()` filtert bewusst auf genau zwei Zustände
(`WAITING_FOR_HANDOFF_TO_EXECUTOR`, `WAITING_FOR_COPY_TO_CONTROL`,
`_BOARD_STATES` in `src/bridge/cli.py`) — "Board ist ein Dirigent, kein
Fortschrittsmonitor" (Abschnitt 6 der Übergabe). Das reicht für den
`task copied`-Button (wirkt auf `WAITING_FOR_COPY_TO_CONTROL`), aber
**nicht** für `task archive` — dessen typischer Ausgangszustand
`REVIEW_REQUIRED` ist im Board gar nicht sichtbar (`state-model.yaml`:
`REVIEW_REQUIRED -> [COMPLETED, APPROVAL_REQUIRED, RUNNING, FAILED,
BLOCKED, ARCHIVED]` — `ARCHIVED` direkt erlaubt, aber die Zeile taucht in
`_BOARD_STATES` nicht auf).

Entscheidung: **Das Board selbst bleibt unverändert** (keine Erweiterung
von `_BOARD_STATES`, kein Rühren an `bridge board`/`_board_text()` für die
CLI). Die Web-UI zeigt zusätzlich, klar optisch abgesetzt (eigene
Überschrift, z. B. "Offene Aufträge außerhalb des Boards"), eine zweite,
schlichtere Liste: alle Aufträge mit Status **nicht** in
`{ARCHIVED}` **und nicht** bereits in der Board-Liste enthalten (Quelle:
vorhandenes `_list_task_docs(store)` bzw. `store.load_task` je ID, gleiche
Grundlage wie `bridge task list`). Diese zweite Liste zeigt nur
`bridge_task_id`, Projekt, Status, Wartezeit — bewusst schlanker als das
Board, kein `Führung/Prüfung` o. Ä. nötig. Aus ihr heraus sind je nach
Status die Buttons `archive` (Status `REVIEW_REQUIRED`,
`APPROVAL_REQUIRED`, `COMPLETED`, `FAILED`, `BLOCKED`, `INTERRUPTED`,
`WAITING_FOR_RESUME` — überall dort, wo `state-model.yaml` einen direkten
Übergang nach `ARCHIVED` erlaubt) und `run finish` (Status `RUNNING`)
aktiv.

## Von Claude Code umzusetzen

### RUN-01 — Lese-Endpunkte

#### 1) Auftrag anlegen und Lauf 1 starten

```
bridge task create tasks/incoming/BRIDGE-0020.yaml
bridge run start BRIDGE-0020 --actor claude-code
```
(Staging-Datei danach löschen.)

#### 2) Neues Modul `src/bridge/webui.py`

Reine stdlib (`http.server`, `json`, `urllib.parse`) — kein neues
Laufzeit-Requirement in `requirements.txt`. Konsistent mit dem Rest des
Projekts ("CLI... reine stdlib", `README.md`).

- `serve(store, *, port, actor, host="127.0.0.1")` startet einen
  `http.server.ThreadingHTTPServer` (ein Request pro gleichzeitigem
  Browser-Tab reicht, kein hoher Durchsatz nötig). **`host` ist im CLI
  nicht überschreibbar** (siehe Punkt 3) — Bindung an `127.0.0.1` ist
  hart, keine externe Erreichbarkeit.
- `GET /` liefert eine einzelne HTML-Seite (inline `<style>`/`<script>`,
  keine externen Assets, kein CDN — funktioniert offline). Auto-Refresh
  per `setInterval` gegen `GET /api/board` alle 15 s (gleicher
  Standardwert wie `bridge board --watch --interval`), kein volles
  Page-Reload.
- `GET /api/board` liefert JSON: `{"board": [...], "other": [...]}`.
  - `board`: exakt die Datenquelle von `_board_rows(store)` — dieselbe
    Funktion importieren und wiederverwenden (`from bridge.cli import
    _board_rows` oder, sauberer, die Board-Datenermittlung aus `cli.py`
    nach `webui.py` extrahieren und von `cli.py` importieren lassen,
    damit `bridge board` und die Web-UI garantiert nie auseinanderlaufen
    — **letzteres bevorzugt**, siehe Akzeptanzkriterien).
  - `other`: die in "Architekturentscheidung" beschriebene Zusatzliste.
  - Jede Zeile enthält zusätzlich das rohe `status`-Feld (damit das
    Frontend weiß, welche Buttons in RUN-02 aktiv sein dürfen) und
    `bridge_task_id` — in RUN-01 werden diese Felder nur mitgeliefert,
    noch nicht für Buttons genutzt.
- Kein Schreibzugriff in RUN-01: 404/405 für alles außer `GET /` und
  `GET /api/board`.
- Fehlerfall (Store/Profil kaputt): JSON-Fehlerobjekt mit `error`-Feld,
  HTTP 500 — kein Stacktrace im Browser, kein Absturz des Servers (ein
  fehlerhafter Request darf den `ThreadingHTTPServer` nicht beenden).

#### 3) CLI-Anbindung (`src/bridge/cli.py`)

Neuer Subcommand:

```
bridge webui serve --actor <a> [--port 8420]
```

- `--host` bewusst **nicht** als Option anbieten (siehe Sicherheits-Notiz
  unten) — Bindung an `127.0.0.1` ist im Code fest verdrahtet, nicht
  konfigurierbar.
- `--port` Standard `8420` (freier, unauffälliger Port; falls belegt:
  klare Fehlermeldung, kein automatisches Ausweichen auf einen anderen
  Port ohne das anzuzeigen).
- `--actor` Pflicht (Muster wie bei allen anderen zustandsändernden
  Kommandos) — wird in RUN-02 als Vorbelegung für das `actor`-Feld der
  Aktions-Buttons verwendet, im Frontend aber editierbar (falls z. B. der
  Mensch statt `human` einen anderen Namen eintragen will).
- Ausgabe beim Start: `Web-UI: http://127.0.0.1:8420/ (nur lokal
  erreichbar, Strg+C zum Beenden)` — kein automatisches Öffnen eines
  Browsertabs (kein neues Verhalten erraten, das der Nutzer nicht
  angefordert hat).
- `Strg+C` beendet sauber (`KeyboardInterrupt` abfangen, wie
  `_board_loop`), kein Traceback.

#### 4) Sicherheits-Notiz (in `webui.py` als Kommentar UND in
`docs/security/SECURITY-MODEL.md` als kurzer neuer Abschnitt "Web-UI
(BRIDGE-020)" ergänzen)

- Bindung ausschließlich `127.0.0.1` — kein `0.0.0.0`, keine
  Host-Option. Das ist die technische Umsetzung von "keine externe
  Erreichbarkeit" aus der Übergabe, nicht nur eine Empfehlung.
- Kein Auth-Layer (bewusst, da nur `localhost`) — das muss explizit so
  dokumentiert sein, damit niemand später versehentlich `--host 0.0.0.0`
  ergänzt, ohne diese Lücke zu bedenken.

#### 5) Tests

- `webui.py`: Unittest, der einen Server auf Port 0 (freier Port vom OS)
  startet, `GET /` und `GET /api/board` per `urllib.request` abruft,
  Inhalt gegen eine präparierte Store-Fixture prüft, Server wieder
  herunterfährt.
- Regressionstest: `_board_rows()`/`bridge board`-Ausgabe unverändert
  (Board-Extraktion aus `cli.py`, falls Punkt 2 die Funktion verschiebt,
  darf **kein** CLI-Verhalten ändern — bestehende Board-Tests müssen ohne
  Anpassung weiter grün sein).

#### 6) Pflicht-Footer + Lauf 1 abschließen

```
bridge run finish BRIDGE-0020 --status COMPLETED --actor claude-code \
  --summary "Stufe 1: lesende Web-UI (GET /, GET /api/board), _board_rows() wiederverwendet, Bindung nur 127.0.0.1, Auto-Refresh 15s."
```

`Auftrag: BRIDGE-0020 / Lauf: RUN-01 / Status: COMPLETED`

---

### RUN-02 — Aktions-Endpunkte mit Bestätigungslogik

Setzt auf RUN-01 auf. Vor Beginn: `bridge run resume BRIDGE-0020 --actor
claude-code`.

#### 1) Neue Endpunkte in `webui.py`

Alle drei zustandsändernden CLI-Kommandos bekommen ein Web-Pendant, das
**dieselbe** darunterliegende Store-/Runner-Logik aufruft (kein
Parallel-Code):

| Endpunkt | Ruft intern auf | Voraussetzung |
|---|---|---|
| `POST /api/task/<id>/copied` | dasselbe wie `bridge task copied` (Store-Statuscheck: nur aus `WAITING_FOR_COPY_TO_CONTROL`) | Body: `{"actor": "...", "confirm": true}` |
| `POST /api/task/<id>/archive` | dasselbe wie `bridge task archive` | Body: `{"actor": "...", "reason": "...", "confirm": true}` (`reason` optional, wie im CLI) |
| `POST /api/run/<id>/finish` | `runner.finish(store, id, status, draft={}, base_head=None, actor=actor, machine=None, summary=summary)` | Body: `{"actor": "...", "status": "...", "summary": "...", "confirm": true}` |

Wichtig für `run finish` über die Web-UI: **kein** `--from draft.yaml`
möglich (das ist Executor-internes Detail, kein Web-Formularfeld) — die
Web-UI liefert daher immer ein leeres `draft` und stützt sich allein auf
`--summary`. Im Frontend als Hinweistext kennzeichnen: "Für reguläre
Auftragsabschlüsse nutzt Claude Code weiterhin `bridge run finish --from
draft.yaml` direkt im Terminal (liefert `acceptance_results` mit). Dieser
Button ist für manuelle/Ausnahme-Abschlüsse (z. B. hängengebliebene
Läufe)." — das entspricht Regel 10 der Übergabe (Guardrail: bei
Scope-Fragen eine konkrete Empfehlung, keine offene Wahl ohne Kontext).

#### 2) Serverseitige Bestätigungspflicht (nicht nur Frontend-Dialog)

- Fehlt `confirm: true` im Body → HTTP 400, keine Zustandsänderung. Der
  Bestätigungsdialog im Browser ist UX, die serverseitige Prüfung ist die
  eigentliche Sicherung (ein Curl-Aufruf ohne `confirm` darf nichts
  auslösen).
- Fehlt `actor` oder ist leer → HTTP 400 (Muster wie `--actor required`
  in allen bestehenden CLI-Kommandos).
- `run finish` zusätzlich: leeres/fehlendes `summary` → HTTP 400 (setzt
  BRIDGE-021 durch — die Web-UI darf die `--summary`-Pflicht aus
  `CLAUDE.md` nicht unterlaufen).
- Jede erfolgreiche Aktion landet automatisch im bestehenden
  `audit/audit.jsonl` (das passiert bereits innerhalb von
  `store.set_status`/`runner.finish` — hier nichts Neues bauen, nur
  sicherstellen, dass der Web-Pfad denselben Code nutzt statt eigene
  Audit-Einträge zu schreiben).

#### 3) Same-Origin-Schutz für POST-Requests

Zusätzliche, einfache Absicherung gegen einen bösartigen Tab in
irgendeinem anderen Browserfenster, der im Hintergrund gegen `localhost`
postet: bei jedem `POST` den `Origin`- bzw. ersatzweise
`Referer`-Header prüfen — muss `http://127.0.0.1:<port>` entsprechen,
sonst HTTP 403. Kein CSRF-Token nötig (Single-User, kein Login), das
reicht als Minimalschutz, ist aber nicht optional.

#### 4) Frontend

- Pro Zeile (Board wie Zusatzliste) die laut Status zulässigen Buttons
  (Tabelle oben). Klick öffnet einen einfachen Bestätigungsdialog
  (`confirm()` reicht, kein aufwändiges Modal nötig) mit Auftrags-ID und
  Aktion im Klartext; bei `run finish` zusätzlich ein Eingabefeld für
  `summary` (Pflichtfeld, Submit-Button erst aktiv bei nicht-leerem Text)
  und eine Auswahl für `status` (Dropdown: `COMPLETED`, `FAILED`,
  `BLOCKED`, `REVIEW_REQUIRED`, `APPROVAL_REQUIRED` — die laut
  `state-model.yaml` aus `RUNNING` erreichbaren Ziele).
- Nach jeder Aktion: `GET /api/board` sofort neu laden (nicht auf den
  nächsten 15-s-Tick warten), Erfolg/Fehler kurz sichtbar einblenden.

#### 5) Tests

- Je Endpunkt: Erfolgsfall, fehlendes `confirm`, fehlender/leerer
  `actor`, falscher Ausgangszustand (z. B. `copied` auf einem Auftrag,
  der nicht in `WAITING_FOR_COPY_TO_CONTROL` steht — muss denselben
  Fehler wie das CLI liefern, nicht stillschweigend ignorieren), falscher
  `Origin`-Header.
- `run finish` zusätzlich: fehlende `summary`.
- Integrationstest über einen laufenden Testserver: `POST` gegen
  `/api/task/<id>/copied`, danach `GET /api/board` prüfen, dass sich der
  Zustand tatsächlich geändert hat (nicht nur HTTP 200 prüfen).
- Regressionstest: alle bisherigen 173+X Tests weiterhin grün, frischer
  Klon verifiziert.

#### 6) Pflicht-Footer + Lauf 2 abschließen

```
bridge run finish BRIDGE-0020 --status COMPLETED --actor claude-code \
  --summary "Stufe 2: Aktions-Endpunkte task copied/archive, run finish, serverseitige Bestätigungspflicht + Same-Origin-Check, Frontend-Buttons je Status."
```

`Auftrag: BRIDGE-0020 / Lauf: RUN-02 / Status: COMPLETED`

## Akzeptanzkriterien

**RUN-01 (Stufe 1):**
- `bridge webui serve --actor <a> [--port N]` startet einen Server, der
  ausschließlich an `127.0.0.1` bindet (kein `--host`-Flag vorhanden).
- `GET /` liefert eine funktionierende HTML-Seite mit Auto-Refresh gegen
  `GET /api/board` (Standard-Intervall 15 s), ohne externe Assets.
- `GET /api/board` liefert die Board-Daten aus derselben Quelle wie
  `bridge board` (keine zweite, potenziell abweichende Implementierung)
  sowie zusätzlich die in der Architekturentscheidung beschriebene
  Zusatzliste `other`.
- `bridge board` (CLI) verhält sich exakt wie vor diesem Paket — keine
  Änderung an `_BOARD_STATES`, `_board_text()`-Format oder Spaltenbreiten.
- Kein Schreibzugriff über die Web-UI in RUN-01 möglich.
- Alle Tests grün (bestehende 173 + neue), frischer Klon verifiziert.

**RUN-02 (Stufe 2):**
- `POST /api/task/<id>/copied`, `.../archive`, `POST /api/run/<id>/finish`
  nutzen dieselbe Store-/Runner-Logik wie die entsprechenden
  CLI-Kommandos — kein Parallel-Code, keine abweichenden Zustandsregeln.
- Jede der drei Aktionen scheitert serverseitig (HTTP 400) ohne
  `confirm: true` und ohne nicht-leeren `actor`; `run finish` zusätzlich
  ohne nicht-leere `summary`.
- `POST`-Requests mit falschem/fehlendem `Origin`/`Referer` werden mit
  HTTP 403 abgelehnt.
- Frontend zeigt Buttons nur für Aufträge/Status, bei denen der
  jeweilige Übergang laut `state-model.yaml` zulässig ist, mit
  Bestätigungsdialog vor jedem Klick.
- Jede über die Web-UI ausgelöste Aktion erscheint korrekt in
  `audit/audit.jsonl` (gleicher Mechanismus wie CLI-Aktionen, kein
  Sonderweg).
- Kein bestehendes CLI-Verhalten (`task copied`/`archive`/`run finish`
  über das Terminal) ändert sich.
- Alle Tests grün (bestehende Basis aus RUN-01 + neue), frischer Klon
  verifiziert.
- `docs/security/SECURITY-MODEL.md` enthält den neuen Abschnitt
  "Web-UI (BRIDGE-020)" mit der `127.0.0.1`-only-Begründung.
