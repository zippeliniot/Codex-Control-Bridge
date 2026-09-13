# CCB — Steuerchat-Referenz: Pflichtlektüre & Bridge-Bedienung

Ergänzt `docs/CCB-STEUERCHAT-ARBEITSWEISE.md` (das *wie* der
Zusammenarbeit) um zwei Dinge im Detail: **was** jede Primärquelle
tatsächlich enthält und **wie** die Bridge — CLI und Web-UI — konkret zu
bedienen ist. Stand: HEAD `0cc2f3f`, gegen den echten Code und die
echten Dateien geprüft (Regel 7/12 aus der Übergabe), keine Vermutungen.

---

## Teil 1 — Pflichtlektüre: welche Datei, was drin steht, worauf achten

Reihenfolge wie im Sitzungsstart-Pflichtablauf (`ARBEITSWEISE.md`
Abschnitt 1). Alle Pfade relativ zum Repo-Root, per frischem Klon lesen
(`bash_tool`+`git clone`, nicht `web_fetch`).

### `CLAUDE.md` (Arbeitsanweisung für Claude Code)
Die *Executor-seitige* Verhaltensvorschrift — direkt an Claude Code
gerichtet, nicht an den Steuerchat, aber der Steuerchat muss sie kennen,
um Aufträge kompatibel zu formulieren. Gliederung:
- **Ausführungsmodell** — Claude Code als native Windows-App.
- **Harte Regeln (nicht verhandelbar)**, wörtlich sieben Stück:
  Ubuntu/WSL nicht verändern, nicht in WSL-Distros hineingreifen,
  Dorfschaft nicht anfassen (außer read-only, BRIDGE-011/012), nur
  innerhalb `E:\_DEV\Codex-Control-Bridge` arbeiten, Fail-closed bei
  Unsicherheit, Least Privilege (kritische Aktionen nie ohne
  ausdrückliche Freigabe), getrennte Nummernräume `BRIDGE-xxx` vs.
  `DORF-xxx`.
- **Maschinen & Wechsel** — welche Maschine welche Rolle hat.
- **Git Push durch Claude Code** — der `GIT_PUSH`-Berechtigungsmechanismus,
  siehe Teil 3 unten.
- **Modellsteuerung, Arbeitsweise, Auftragsabschluss (Pflicht-Footer),
  `run finish`-Zusammenfassung, Python-Umgebung, Checkpoint & Resume,
  Heartbeat an Checkpoints.**

### `docs/architecture/ARCHITECTURE.md` (verbindliche Architekturgrundlage)
Die technische Gesamtsicht, 15 Abschnitte: Zweck, logische Komponenten,
Kommunikationsprinzip (neutraler Übergabekanal), Identität eines
Auftrags, Zustandsmodell, Lauf-/Resume-Modell, Sicherheitsmodell
(verbindlich), Git-Sicherheit, Maschinenmodell, Ergebnisintegrität &
Audit, Speicherung, Projektunabhängigkeit, Modellsteuerung,
Entwicklungsstufen, und zum Schluss eine Zusammenfassung der bindenden
Leitregeln. Das ist die Quelle, gegen die eine neue Spezifikation
architektonisch passen muss — nicht nur gegen ein Schema.

### `docs/security/SECURITY-MODEL.md` (Rechtestufen, Fail-closed, Git-Sicherheit)
Sechs Hauptabschnitte, davon zwei inzwischen mit Unterabschnitten:
- **1. Grundsatz: Least Privilege**
- **2. Rechtestufen** — welche Berechtigungen (`WORKTREE_WRITE`,
  `TEST_EXECUTION`, `GIT_PUSH`, ...) was erlauben.
- **3. Kritische Aktionen — nie implizit** — Merge, Deploy,
  Datenbankänderungen, Force-Push, Produktions-Migration: nie ohne
  ausdrückliche, auftragsgebundene Freigabe, nie aus einer schwächeren
  Stufe abgeleitet.
- **4. Fail-closed** — die Liste der Situationen, in denen angehalten
  statt improvisiert wird (falscher Branch, unerwarteter HEAD, fehlende
  Ausgangslage etc.).
- **5. Git-Sicherheit** (allgemein) mit zwei Unterabschnitten:
  - **5a. Web-UI (BRIDGE-020)** — Grundprinzip: nur an `127.0.0.1`
    gebunden, kein Auth-Layer, weil ursprünglich rein lesend bzw. nur
    Store-Dateioperationen ohne Git.
  - **5b. Web-UI: Git-Commit und Push nach Aktionen (BRIDGE-024)** —
    die Erweiterung, die das ändert: automatischer Commit+Push nach
    `copied`/`archive`/`finish`, abgesichert durch Datei-Whitelist,
    Branch-Prüfung, kategorisches `--force`-Verbot.
  - **5c. CLI: `--commit`-Flag und `base_head`-Fail-closed
    (BRIDGE-025)** — dieselbe Whitelist-Logik (`gitops.py`), jetzt auch
    aus der CLI nutzbar, aber lokal (kein Auto-Push), plus der Fix für
    das stille `changed_files`-Degradieren.
- **6. Grenzen der ersten Version (Nicht-Ziele)**.

### `docs/PROJEKTKONZEPT.md` (fachliche Grundlage, ~1150 Zeilen)
Das umfangreichste Dokument, 31 nummerierte Abschnitte — von der
Ausgangssituation (1) und dem Hauptziel (2) über Auftragsschema (5),
Ergebnisformat (6), Zustandsmodell (7), Umgang mit Usage-Limits und
Unterbrechungen (8), Erkennung eines abgeschlossenen Codex-Auftrags in
drei Stufen (9), Kommunikationsprinzip (10), Projektunabhängigkeit
(11), Maschinenmodell (12), Sicherheitsmodell (13), Git-Sicherheit
(14), Ergebnisintegrität (15), Audit (16), Speicherung (17),
Repositorystruktur (18), bis zu den Entwicklungsstufen 0–3 (19–21),
dem Integrationsziel Dorfschaft (22–24), Handover (25), Fehlerprinzip
(26), Modellsteuerung (27), Multi-Agenten (28) und den
Akzeptanzkriterien (29–31). Bei einer neuen fachlichen Frage (nicht nur
technischer Umsetzung) ist das die erste Anlaufstelle — nicht raten,
den passenden Abschnitt gezielt nachlesen.

### `docs/CCB-STEUERCHAT-ARBEITSWEISE.md` (generell, nicht zustandsspezifisch)
Beschreibt *wie* der Steuerchat arbeitet: Sitzungsstart-Pflichtablauf,
Ein-Auftrag-zur-Zeit-Disziplin, Datei-statt-Copy-Paste-Konvention,
CCB-Kurzreferenz, Verifikationspflichten (inkl. der Tatsache, dass der
Steuerchat selbst keine Push-Credentials für GitHub hat). Dieses
Dokument hier (`CCB-STEUERCHAT-REFERENZ.md`) ist die inhaltliche
Ergänzung dazu — Detailwissen statt Verhaltensregeln.

### `docs/handover/CCB-UEBERGABE-vX.md` (jeweils aktuellste Version)
Der laufende Projektstand — welche `BRIDGE-xxxx`-IDs archiviert sind,
was zuletzt gebaut wurde, was als Nächstes offen ist. Ändert sich mit
jeder Sitzung, im Gegensatz zu den übrigen Dokumenten hier.

### Bei Bedarf zusätzlich
- **`CONTROL.md`** — nur relevant bei Fragen zur Codex-/ChatGPT-Steuerprozess-Seite.
- **`docs/architecture/machines.md`** — Maschinenregister (HAM11/DES11,
  Rollen, Rotation) — **jetzt konkret relevant, siehe Hinweis am Ende
  dieses Dokuments.**

### `schemas/` — Pflichtfelder nicht aus dem Gedächtnis rekonstruieren
- **`schemas/task.schema.yaml`** — Pflichtfelder eines Auftrags
  (`bridge_task_id`, `project_id`, `title`, `description`, `task_class`,
  `repository`, `branch`, `permissions`, `status`, `created_at`,
  `created_by`, `acceptance_criteria`, optional `git.expected_head`,
  `depends_on`). Optionales Feld `priority` (Enum `LOW`/`MEDIUM`/`HIGH`,
  Default `MEDIUM`; kein `null` — jeder Auftrag hat eine Priorität;
  setzbar über `bridge task set-priority`, BRIDGE-028).
- **`schemas/state-model.yaml`** — die **einzige** Quelle der erlaubten
  Zustandsübergänge (siehe Teil 2 unten, vollständig wiedergegeben).
- Weitere Schema-Dateien je nach Bedarf des Auftrags über `ls schemas/`
  ermitteln.

---

## Teil 2 — Zustandsmodell (SSOT: `schemas/state-model.yaml`)

**Alle 14 Zustände**, ein einziger Endzustand:

```
CREATED, READY, WAITING_FOR_HANDOFF_TO_EXECUTOR, CLAIMED, RUNNING,
INTERRUPTED, WAITING_FOR_RESUME, COMPLETED, WAITING_FOR_COPY_TO_CONTROL,
FAILED, BLOCKED, REVIEW_REQUIRED, APPROVAL_REQUIRED, ARCHIVED (terminal)
```

**Wichtiges Prinzip, wörtlich aus der Schema-Datei:** `COMPLETED`
bedeutet „Ergebnisvertrag erfüllt", **nicht** „fachlich freigegeben" —
deshalb ist `COMPLETED` nicht terminal, sondern kann weiter nach
`REVIEW_REQUIRED`/Archiv übergehen. Die fachliche Prüfung ist immer
Aufgabe des Steuerchats, nie automatisch.

**Erlaubte Übergänge** (vollständige Tabelle):

| Von | Nach |
|---|---|
| `CREATED` | `READY`, `BLOCKED`, `ARCHIVED` |
| `READY` | `WAITING_FOR_HANDOFF_TO_EXECUTOR`, `CLAIMED`, `BLOCKED`, `ARCHIVED` |
| `WAITING_FOR_HANDOFF_TO_EXECUTOR` | `CLAIMED`, `BLOCKED`, `ARCHIVED` |
| `CLAIMED` | `RUNNING`, `BLOCKED`, `FAILED`, `ARCHIVED` |
| `RUNNING` | `COMPLETED`, `FAILED`, `BLOCKED`, `INTERRUPTED`, `REVIEW_REQUIRED`, `APPROVAL_REQUIRED` |
| `INTERRUPTED` | `WAITING_FOR_RESUME`, `FAILED`, `BLOCKED`, `ARCHIVED` |
| `WAITING_FOR_RESUME` | `CLAIMED`, `RUNNING`, `BLOCKED`, `ARCHIVED` |
| `COMPLETED` | `WAITING_FOR_COPY_TO_CONTROL`, `REVIEW_REQUIRED`, `ARCHIVED` |
| `WAITING_FOR_COPY_TO_CONTROL` | `REVIEW_REQUIRED`, `ARCHIVED` |
| `REVIEW_REQUIRED` | `COMPLETED`, `APPROVAL_REQUIRED`, `RUNNING`, `FAILED`, `BLOCKED`, `ARCHIVED` |
| `APPROVAL_REQUIRED` | `COMPLETED`, `RUNNING`, `FAILED`, `BLOCKED`, `ARCHIVED` |
| `FAILED` | `READY`, `BLOCKED`, `ARCHIVED` |
| `BLOCKED` | `READY`, `FAILED`, `ARCHIVED` |
| `ARCHIVED` | *(keine — Endzustand)* |

`WAITING_FOR_HANDOFF_TO_EXECUTOR` (Richtung Steuerchat → Executor) und
`WAITING_FOR_COPY_TO_CONTROL` (Richtung Executor → Steuerchat) sind
bewusst reine Wartepunkte **ohne** inhaltliche Prüfung — genau die
beiden, die das Board anzeigt (Regel 5 der Übergabe). Die
Direkt-Übergänge (`READY`→`CLAIMED`, `COMPLETED`→`REVIEW_REQUIRED`)
bleiben aus Abwärtskompatibilität zusätzlich erlaubt.

Der typische Weg, den ein Auftrag in diesem Setup durchläuft:
```
CREATED → RUNNING → COMPLETED → WAITING_FOR_COPY_TO_CONTROL
        → REVIEW_REQUIRED → ARCHIVED
```

---

## Teil 3 — CLI-Referenz (vollständig, aus `cli.py` extrahiert)

**Aufrufform (immer):**
```
.venv\Scripts\python.exe src\bridge\cli.py --root . --schema-dir schemas <befehl>
```

### `task` — Aufträge verwalten
| Befehl | Zweck | Wichtige Flags |
|---|---|---|
| `task create <path>` | Auftrag aus Staging-YAML im Store anlegen | `--commit` (BRIDGE-025, lokal, kein Push) |
| `task show <id>` | Status + Kernfelder | — |
| `task list` | alle Aufträge mit Status | — |
| `task copied <id>` | Ergebnis „in Steuerchat kopiert" (Executor→Steuerchat-Wartepunkt auflösen) | `--actor` (Pflicht), `--commit` |
| `task archive <id>` | Auftrag archivieren (Endzustand) | `--actor`, `--reason`, `--commit` |
| `task set-priority <id> <LOW\|MEDIUM\|HIGH>` | Priorität setzen (BRIDGE-028) | `--actor` (Pflicht) |
| `task set-status <id> <status>` | direkter Zustandswechsel (Ausnahme, nicht Regelweg) | `--actor`, `--machine`, `--reason` |

### `run` — Lauf-Lebenszyklus
| Befehl | Zweck | Wichtige Flags |
|---|---|---|
| `run start <id>` | Lauf starten (→ `RUNNING`, initialer Heartbeat) | `--actor` (Pflicht), `--commit` |
| `run beat <id>` | Heartbeat des aktuellen Laufs aktualisieren | `--actor` (Pflicht) |
| `run finish <id>` | Lauf abschließen (Ergebnis-Import + Zustandswechsel) | `--status` (Pflicht), `--from <draft.yaml>`, `--base-head` (bei Fehlen automatisch aus `task.yaml`→`git.expected_head`, sonst fail-closed, BRIDGE-025), `--actor` (Pflicht), `--summary`, `--commit` |
| `run resume <id>` | Lauf wiederaufnehmen (→ `RUNNING`, neuer RUN) | `--actor` (Pflicht) |

### `result` — Ergebnisse verwalten
| Befehl | Zweck |
|---|---|
| `result write <path>` | Ergebnis-YAML direkt ablegen |
| `result import` | Ergebnis aus Entwurf (`draft.yaml`) + automatischer Git-Provenienz importieren (das, was `run finish --from` intern nutzt) |

### Lesend / Diagnose (nie Store-verändernd)
| Befehl | Zweck |
|---|---|
| `audit show [<id>]` | Auditspur ausgeben (alle oder ein Auftrag) |
| `resume <id>` | Wiederaufsetz-Hilfe, rein lesend |
| `board [--watch] [--interval N]` | Copy-Paste-Board: welcher Auftrag wartet auf Kopie — **CLI-Version des Web-UI-Boards**, gleiche Zwei-Wartezustände-Logik |
| `overview [--project <id>]` | **Gesamtübersicht:** alle Aufträge, alle Zustände (auch `RUNNING`/`CLAIMED`), mit letzter bekannter Maschine — aktive Aufträge oben, inaktive (kein HB seit 30 Min. oder `WAITING_FOR_RESUME`/`INTERRUPTED`) darunter |
| `commands` | Befehlsreferenz mit aufgelöstem lokalem Pfad |
| `validate` | Task/Result gegen Schema prüfen |
| `next-run <id>` | nächste Lauf-ID ermitteln |
| `project list` / `project show <id>` / `project validate <path>` | Projektprofile (Adapter) |

### `webui serve` — lokale Web-UI starten
```
.venv\Scripts\python.exe src\bridge\cli.py --root . --schema-dir schemas webui serve --actor <name> [--port 8420]
```
`--actor` ist **Pflicht** (Vorbelegung für die Aktions-Buttons). Bindet
hart an `127.0.0.1`, kein `--host`-Flag — bewusst kein Fernzugriff
möglich.

### `watch` — automatischer Beobachter (Stufe 2/3, aktuell selten genutzt)
| Befehl | Zweck |
|---|---|
| `watch scan [--apply] [--task <id>]` | einmalig prüfen; ohne `--apply` reiner Trockenlauf |
| `watch loop --interval N [--apply]` | wiederholt prüfen bis Ctrl+C |
| `watch heartbeat <id> <run_id>` | Heartbeat eines Laufs schreiben/aktualisieren |

### Exit-Codes
- `0` — Erfolg.
- `1` — fachlicher Fehler (z. B. `base_head` fehlt und `git.expected_head`
  auch, fail-closed, BRIDGE-025).
- `2` — Nutzungsfehler (z. B. `--status` fehlt).
- `3` — Git-Whitelist-/Branch-Fehler bei `--commit` (BRIDGE-025); die
  Store-Aktion selbst bleibt dabei bestehen, wird nicht zurückgerollt.

---

## Teil 4 — Web-UI-Referenz

**Start:** siehe `webui serve` oben. **URL:** `http://127.0.0.1:8420`.

**Was sie zeigt:**
- **Board — wartet auf Weitergabe/Kopie:** ausschließlich Aufträge in
  `WAITING_FOR_HANDOFF_TO_EXECUTOR` oder `WAITING_FOR_COPY_TO_CONTROL`
  (Spalte „Richtung" zeigt welche). Läuft ein Auftrag gerade
  (`RUNNING`/`CLAIMED`), erscheint er dort **nicht** — das ist Absicht,
  nicht ein Bug (Regel 5 der Übergabe).
- **Offene Aufträge außerhalb des Boards:** alle anderen nicht-terminalen
  Zustände (`REVIEW_REQUIRED` etc.), mit passenden Aktionen.
- **Alle Projekte — Gesamtübersicht** (seit BRIDGE-026, Endpunkt
  `GET /api/overview`): alle Aufträge über **alle** Zustände, inkl.
  `RUNNING`/`CLAIMED` — genau was das Board bewusst versteckt. Spalten:
  Projekt, Auftrag, Status, **Maschine** (letzte bekannte, `?` wo
  kein `--machine`-Flag übergeben wurde), letzte Aktivität (Heartbeat-
  Alter). Aktive Aufträge (`RUNNING`/`CLAIMED` + HB < 30 Min.) oben,
  inaktive (staler HB, `WAITING_FOR_RESUME`, `INTERRUPTED`) darunter
  mit Trennlinie. Der Client-Filter gilt auch hier. Dasselbe Ergebnis
  wie `bridge overview --project <id>` im Terminal.
- **Persistenter, scrollbarer Aktions-Log** (seit BRIDGE-023): jede
  ausgeführte Aktion mit Zeitstempel, Aktion, betroffener ID und
  Ergebnis — bleibt über Auto-Refresh-Ticks erhalten, wird **nicht**
  vom 15-Sekunden-Refresh überschrieben.
- **Client-Filter** (seit BRIDGE-023): Projekt/Status/Auftrags-ID,
  überlebt Auto-Refresh, kein neuer Server-Endpoint dahinter. Gilt
  jetzt auch für die Gesamtübersicht.

**Aktions-Buttons** (`Kopiert → Review`, `Archivieren`, `Lauf
abschließen`): rufen serverseitig **dieselbe** Store-/Runner-Logik wie
die entsprechenden CLI-Befehle auf — kein Parallel-Code. Verlangen
`confirm`+`actor`+Same-Origin (fail-closed bei Verstoß). **Seit
BRIDGE-024 zusätzlich:** nach erfolgreicher Aktion wird automatisch
`git commit` **und** `git push` ausgeführt, abgesichert durch eine feste
Datei-Whitelist pro Aktionstyp, Branch-Prüfung (nur `main`) und
kategorisches `--force`-Verbot. Der Log-Eintrag zeigt das Ergebnis
direkt (`→ committed <sha>, gepusht` bzw. Fehlertext bei
Push-Fehlschlag, Commit bleibt dann lokal).

**Push-Retry (BRIDGE-029):** Schlägt der Auto-Push mit Non-Fast-Forward
fehl (gleichzeitiger Commit einer anderen Maschine/Session), macht die
Web-UI **genau einen** automatischen Ausgleichsversuch: `git fetch` +
`git rebase origin/main` + erneuter Push. Gelingt der Rebase und der
zweite Push → Log zeigt `gepusht (nach Rebase)`, `retried: true`. Kommt
es zum Rebase-Konflikt → `rebase --abort`, Commit bleibt lokal (Log
zeigt Fehlertext), kein Force-Push. Andere Fehler (kein Remote, Auth)
lösen keinen Retry aus. Maximal ein Retry-Versuch; Details in
`docs/security/SECURITY-MODEL.md` Abschnitt 5c.

**Prioritätszuweisung** (seit BRIDGE-028): In der Gesamtübersicht
(`/api/overview`) enthält jede Auftragszeile ein `<select>`-Dropdown
(`HIGH`/`MEDIUM`/`LOW`). Eine Änderung sendet `POST
/api/task/<id>/priority` mit `{actor, confirm: true, priority}` und
schreibt denselben `Store.set_priority()`-Aufruf wie `bridge task
set-priority` — kein Parallel-Code. Prioritätsänderungen lösen **keinen**
Auto-Commit/Push aus (kein Zustandswechsel, nur Metadaten-Update).
Fehlende Priorität in bestehenden Aufträgen wird als `MEDIUM` angezeigt.

**Wichtige Grenze, die in dieser Sitzung real zu Verwirrung führte:**
Die Web-UI zeigt **ausschließlich den Store-Zustand** — den Inhalt von
`task.yaml`, wie er gerade auf der Platte liegt. Sie hat **keinen**
Einblick in den Git-Verlauf selbst (ob etwas committet/gepusht wurde,
außer durch ihre eigenen Aktions-Buttons). Für die Frage „ist das
wirklich auf `origin/main`?" ist immer ein frischer Klon nötig (Regel
6), nicht die Web-UI-Anzeige allein.

---

## Teil 5 — Typischer Steuerchat-Workflow, Ende-zu-Ende

1. Frischer Klon, Primärquellen lesen, ID-Lage prüfen (Sitzungsstart-
   Pflichtablauf, `ARBEITSWEISE.md`).
2. Work-Package (`work-packages/BRIDGE-0XX.md`) + Staging-YAML
   (`tasks/incoming/BRIDGE-0XX.yaml`) als **Datei zum Download**
   erzeugen, mit Sicherheitsentscheid/Kontext gegen den echten Code
   geprüft (Regel 7).
3. Nutzer legt beide Dateien via PowerShell ab, committet/pusht das
   Work-Package (Staging-YAML bleibt lokal, `.gitignore`d).
4. Claude Code (native App, empfohlener Modus `auto`) arbeitet den
   Auftrag ab: `task create` → `run start` → Implementierung in kleinen
   Schritten → `run finish --commit --summary "..."` → `git push`.
5. Steuerchat verifiziert **vollständig**, nicht nur den Pflicht-Footer:
   frischer Klon, Tests im isolierten `.venv` laufen lassen, Diff gegen
   die Akzeptanzkriterien prüfen, `result.yaml`/`changed_files` auf
   Vollständigkeit prüfen.
6. Nutzer schließt über Web-UI oder CLI ab (`Kopiert → Review`, dann
   `Archivieren`) — Web-UI committet/pusht das jetzt automatisch selbst.
7. Steuerchat verifiziert den Abschluss final per frischem Klon.
8. Erst danach der nächste Auftrag (Ein-Auftrag-zur-Zeit-Disziplin).

---

## Hinweis zum Maschinenwechsel (dieser Chat, 10.09.2026)

April hat angegeben, ab jetzt auf **DES11** weiterzuarbeiten (nicht
mehr auf der Maschine, auf der BRIDGE-023/024/025 liefen). Laut
`CLAUDE.md`/`docs/architecture/machines.md` gibt es ein Maschinenregister
mit definierten Rollen — bei einem echten Maschinenwechsel gilt Regel 9
der Übergabe: **RUN-Nummern sind kein Ort**, und die Bridge trackt nicht
fensterscharf, welche Maschine an welchem Auftrag arbeitet. Konkret vor
dem nächsten Auftrag zu klären, nicht anzunehmen:
- Ist `E:\_DEV\Codex-Control-Bridge` auf DES11 derselbe geklonte Pfad,
  oder ein separater Klon?
- Läuft dort ebenfalls ein `.venv` mit denselben Requirements, oder
  muss das neu aufgesetzt werden?
- Git-Credentials für `origin` auf DES11 vorhanden (Push-Fähigkeit),
  wie bisher auf der anderen Maschine?
Ich nehme hier nichts an, was nicht bestätigt ist (keine Dichtungen,
Regel 12/15) — bei Bedarf `docs/architecture/machines.md` gemeinsam
durchgehen, statt zu raten.
