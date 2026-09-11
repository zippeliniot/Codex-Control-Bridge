# BRIDGE-026 — Gesamtübersicht: alle Aufträge, alle Zustände, mit Maschine

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0026 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| review_roles | lead: anthropic, support: openai (aus Projektprofil übernommen) |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM — neue Anzeige-/Aggregationslogik auf bestehenden, bereits vorhandenen Daten (kein neues Datenfeld, kein State-Model-Eingriff). |

> **Verbindlich für diesen und jeden CCB-Auftrag:**
> - Jede Zustandsänderung läuft über die Bridge-CLI, kein direktes Bearbeiten
>   von Store-Dateien.
> - `GIT_PUSH` steht im Profil — nach `run finish` **muss** gepusht werden,
>   idealerweise über `--commit` (BRIDGE-025), und **sofort**, nicht gesammelt
>   (siehe `CLAUDE.md` „Checkpoint & Resume" Punkt 4, verschärft 12.09.2026).

## Kontext

Bei mehreren parallel laufenden Projekten (`dorfschaft`, `wetter-app`,
`climac`, `tanken-monitor`, `bess-msrechner`, `bess-platform`,
`codex-control-bridge`) auf zwei Maschinen (`HAM11`/`DES11`) reicht das
bestehende Board **nicht** aus, um den Überblick zu behalten — und zwar
bewusst nicht, nicht aus Versehen:

- `bridge board`/Web-UI-Board zeigt laut Design (BRIDGE-020, Regel 5 der
  Übergabe) **ausschließlich** die beiden Wartezustände
  `WAITING_FOR_HANDOFF_TO_EXECUTOR` und `WAITING_FOR_COPY_TO_CONTROL`.
  Aufträge in `RUNNING`/`CLAIMED` — also genau die, die *gerade aktiv auf
  einer Maschine laufen* — werden dort absichtlich **nicht** angezeigt.
- Die Rohdaten für „welche Maschine, wann zuletzt aktiv" existieren
  bereits: jedes `set_status`/jeder Heartbeat trägt ein optionales
  `machine`-Feld (`store.py`, `heartbeat.py`). **Aber:** dieses Feld wird
  nur befüllt, wenn `--machine` beim jeweiligen CLI-Aufruf tatsächlich
  übergeben wird — Stichprobe an einer echten `heartbeat.json` in diesem
  Repo zeigt, dass es dort **fehlt** (kein `machine`-Schlüssel). Diese
  Übersicht kann also nur so gut sein wie die tatsächlich übergebenen
  `--machine`-Werte — sie erfindet nichts, zeigt `?` wo Daten fehlen.

**Bewusst nicht in diesem Auftrag:** kein neuer Zustand `PAUSED` im
`schemas/state-model.yaml` (das wäre ein SSOT-Eingriff in die
Zustandsmaschine, hohes Risiko, eigene Design-Entscheidung nötig). „Pausiert
wirkende" Aufträge werden stattdessen **über Inaktivität** erkannt (kein
Heartbeat seit X Minuten trotz `RUNNING`, oder Zustand
`WAITING_FOR_RESUME`/`INTERRUPTED`) und in der Anzeige nach unten sortiert
— keine neue Zustandssemantik, nur eine Sortier-/Darstellungsregel.

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0026.yaml
   bridge run start BRIDGE-0026 --actor claude-code
   ```

2. **Neuer CLI-Befehl `bridge overview`** (`src/bridge/cli.py`, neuer
   Subparser, analog zu `board`):
   - Iteriert über **alle** Aufträge (`_list_task_docs`, wiederverwenden —
     keine neue Store-Abfrage erfinden), **ohne** Zustandsfilter (anders
     als `_board_rows`, das bewusst auf `_BOARD_STATES` einschränkt).
   - Pro Auftrag: `bridge_task_id`, `project_id`/`task_prefix`
     (`_board_project` wiederverwenden), `status`, letzte bekannte
     `machine` (aus dem letzten Audit-Event bzw. `heartbeat.json` des
     aktuellen Laufs — im Funktionscode von `store.py`/`heartbeat.py`
     nachsehen, wie der letzte Wert zuverlässig ermittelt wird, nicht
     raten), Zeitpunkt der letzten Aktivität, `review_roles`
     (`_board_review_roles` wiederverwenden).
   - **Sortierung:** aktive/kürzlich aktive Aufträge oben, inaktive unten.
     Konkrete Inaktivitäts-Schwelle als Konstante definieren (z. B. kein
     Heartbeat seit 30 Minuten trotz `RUNNING`) und im Code/Doku
     begründen, nicht willkürlich raten.
   - `--project <id>`-Filter optional, analog zu bestehenden Mustern.
   - Rein lesend, keine Store-Änderung — wie `board`.

3. **Web-UI erweitern** (`src/bridge/webui.py`, `_PAGE`-Template): neuer
   Abschnitt/Tab „Alle Projekte" oder eigener Bereich unterhalb des
   bestehenden Boards, der dieselben Daten wie `bridge overview` über
   einen neuen Read-Endpunkt zeigt (analog `board_payload()`). **Bestehende
   Funktionen bleiben vollständig erhalten** — Board, Aktions-Buttons
   (`Kopiert → Review`/`Archivieren`/`Lauf abschließen`, inkl.
   Auto-Commit+Push aus BRIDGE-024), persistenter Log und Filter aus
   BRIDGE-023 werden **nicht** ersetzt, nur ergänzt.
   - Visuelle Trennung: aktive Projekte oben, inaktive/pausiert wirkende
     unten (gleiche Logik wie Schritt 2, nicht zweimal unterschiedlich
     implementieren — eine gemeinsame Funktion in `cli.py` oder einem
     neuen kleinen Modul, von CLI und Web-UI gleichermaßen genutzt).
   - Auto-Refresh (15s) darf auch hier Filter/Fokus nicht stören (gleiche
     Disziplin wie BRIDGE-023).

4. Tests (`tests/test_cli.py`/`tests/test_webui.py`, neue Fälle):
   - `overview` zeigt Aufträge in `RUNNING`/`CLAIMED` (die das Board
     bewusst versteckt) — Abgrenzungstest gegen `board`.
   - Sortierung: aktiver Auftrag oben, inaktiver (simulierter alter
     Heartbeat oder `WAITING_FOR_RESUME`) unten.
   - Fehlendes `machine`-Feld wird als `?` angezeigt, nicht als Fehler.
   - Bestehende Tests (`WebUiReadTests`, `WebUiActionTests`,
     `WebUiCliTests`, `WebUiFrontendTests`, `WebUiGitActionTests`)
     weiterhin grün.

5. `docs/CCB-STEUERCHAT-REFERENZ.md` Teil 3/4 um `bridge overview` und den
   neuen Web-UI-Bereich ergänzen (Referenz ist sonst veraltet).

6. Pflicht-Footer + Abschluss, `--commit` nutzen (BRIDGE-025), **sofort
   pushen** nach jedem Commit (nicht sammeln, siehe verschärfte Regel):
   ```
   bridge run finish BRIDGE-0026 --status COMPLETED --actor claude-code \
     --commit \
     --summary "Neuer Befehl 'bridge overview' + Web-UI-Bereich zeigen alle Auftraege/Zustaende inkl. RUNNING mit letzter bekannter Maschine, sortiert aktiv-oben/inaktiv-unten ohne neuen Zustand im state-model. Bestehende Board-/Aktions-Funktionen unveraendert erhalten."
   git push
   ```
   `Auftrag: BRIDGE-0026 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [ ] `bridge overview` zeigt alle Aufträge, alle Zustände (inkl.
      `RUNNING`/`CLAIMED`, die das Board bewusst versteckt).
- [ ] Maschine wird angezeigt, wo bekannt; `?` wo das `machine`-Feld fehlt
      (kein Erfinden von Werten).
- [ ] Aktive Aufträge oben, inaktive (Heartbeat-Schwelle oder
      `WAITING_FOR_RESUME`/`INTERRUPTED`) unten — Schwelle dokumentiert,
      nicht willkürlich.
- [ ] Web-UI zeigt dieselbe Übersicht zusätzlich zum bestehenden Board,
      ersetzt nichts Bestehendes.
- [ ] Bestehende Aktions-Funktionen (Kopiert→Review, Archivieren, Lauf
      abschließen, Auto-Commit+Push, persistenter Log, Filter) unverändert
      funktionsfähig.
- [ ] Kein neuer Zustand im `schemas/state-model.yaml`.
- [ ] `CCB-STEUERCHAT-REFERENZ.md` aktualisiert.
- [ ] Bestehende Tests weiterhin grün, neue Tests grün.
- [ ] Alle Tests grün (bestehende Basis + neue), frischer Klon verifiziert.
- [ ] Jeder Commit sofort gepusht, nicht gesammelt (verschärfte Regel).
