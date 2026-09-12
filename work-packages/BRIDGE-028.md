# BRIDGE-028 — Prioritätsfeld: Schema, CLI, Web-UI-Zuweisung, Sortierung

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0028 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| review_roles | lead: anthropic, support: openai (aus Projektprofil übernommen) |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM — neues optionales Feld + ein neuer CLI-Befehl + eine kleine Audit-Schema-Erweiterung, kein Eingriff in state-model.yaml. |

> **Verbindlich für diesen und jeden CCB-Auftrag:**
> - Jede Zustandsänderung läuft über die Bridge-CLI, kein direktes Bearbeiten
>   von Store-Dateien.
> - `GIT_PUSH` steht im Profil — nach `run finish` **muss** gepusht werden,
>   idealerweise über `--commit` (BRIDGE-025), und **sofort**, nicht gesammelt
>   (siehe `CLAUDE.md` „Checkpoint & Resume" Punkt 4, verschärft 12.09.2026).

## Kontext

Umsetzt Frage 2 aus `docs/CCB-ORCHESTRATOR-KONZEPT.md` (in der Steuerchat-
Sitzung vom 12.09.2026 entschieden, BRIDGE-0027 dokumentiert): Stufen
`LOW`/`MEDIUM`/`HIGH` (kein `URGENT`), Default `MEDIUM`, **manuelle**
Zuweisung über das Web-GUI. Erster Baustein der Roadmap nach BRIDGE-0027.

**Vor der Spezifikation gegen den echten Code geprüft** (nicht nur gegen
Schema/Doku, Verifikationspflicht Nr. 3 aus `CCB-STEUERCHAT-ARBEITSWEISE.md`):

1. Es gibt bewusst **keinen** generischen `task edit`-Befehl (dokumentiert
   in `CCB-STEUERCHAT-REFERENZ.md`, Teil 4, und im Code selbst nicht
   vorhanden). `set-priority` braucht deshalb eine **eigene** neue
   `Store`-Methode, nicht die Wiederverwendung von `set_status`
   (`state_machine.assert_transition` ist für Task-**Status**-Übergänge
   gedacht, nicht für ein unabhängiges Feld wie `priority`).
2. `schemas/audit-event.schema.yaml`: `event_type`-Enum enthält aktuell
   keinen Typ für eine reine Prioritätsänderung, und `old_state`/
   `new_state` sind auf die 14 Task-Status-Werte eingeschränkt — eine
   Prioritätsänderung passt dort nicht rein. **Kleine Schema-Erweiterung
   nötig:** neuer `event_type: PRIORITY_CHANGED` im Enum; alt/neuer
   Prioritätswert wird im bereits vorhandenen freien `reason`-Textfeld
   dokumentiert (z. B. `"LOW -> HIGH"`), nicht in `old_state`/`new_state`.
3. `_overview_rows` (`src/bridge/cli.py`) sortiert aktuell
   `(0 falls aktiv sonst 1, -letzter_Aktivitaets_Zeitstempel)`. Deine
   Entscheidung „Priorität als Zusatzkriterium innerhalb der
   Aktiv/Inaktiv-Gruppierung" fügt sich als dritte Ebene sauber ein:
   `(Gruppe, Prioritaets_Rang, -Zeitstempel)` — Gruppierung bleibt
   unverändert primär, Zeit bleibt finaler Tie-Breaker, Priorität liegt
   dazwischen.
4. `_board_rows` (dasselbe Modul) hat **keine** Aktiv/Inaktiv-Gruppierung
   (das Board zeigt nur die zwei Wartezustände, sortiert bisher rein
   alphabetisch nach `bridge_task_id`). Deine Vorgabe lässt sich dort
   nicht 1:1 übertragen — **Annahme, die hiermit explizit benannt wird:**
   Priorität wird dem bestehenden alphabetischen Sortierschlüssel
   vorangestellt: `(Prioritaets_Rang, bridge_task_id)`. Sollte das nicht
   gewünscht sein (z. B. Board bleibt bewusst rein alphabetisch, ohne
   Priorität), bitte vor Abschluss der Implementierung korrigieren.

**Bewusst nicht in diesem Auftrag** (Roadmap-Reihenfolge einhalten):
Git-Push-Retry (BRIDGE-0029), Review-Unternummern-Schema (BRIDGE-0030),
die eigentliche Orchestrator-Auslöselogik (BRIDGE-0031).

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0028.yaml
   bridge run start BRIDGE-0028 --actor claude-code
   ```

2. **`schemas/task.schema.yaml` erweitern:** neues optionales Feld
   `priority` (Enum `LOW`/`MEDIUM`/`HIGH`, `default: MEDIUM`), analog zur
   bestehenden `reasoning_level`-Konvention (dort `[LOW, MEDIUM, HIGH,
   null]` mit `default: null` — hier bewusst **kein** `null` im Enum, da
   jeder Auftrag eine Priorität mit sinnvollem Default haben soll, nicht
   „keine"). Rückwärtskompatibel: bestehende `task.yaml`-Dateien ohne das
   Feld müssen weiterhin valide sein (Default greift beim Fehlen).

3. **`schemas/audit-event.schema.yaml` erweitern:** `event_type`-Enum um
   `PRIORITY_CHANGED` ergänzen. Kein Eingriff in `old_state`/`new_state`
   nötig — die Prioritätswerte wandern ins bestehende `reason`-Feld.

4. **Neue `Store`-Methode** (`src/bridge/store.py`, analog zu `set_status`,
   aber ohne `state_machine`-Bezug): lädt den Auftrag, validiert die neue
   Priorität gegen das Schema-Enum, schreibt sie ins Dokument, validiert
   das gesamte Dokument erneut (`self.validate`/`save_task`
   wiederverwenden), schreibt einen `PRIORITY_CHANGED`-Audit-Eintrag mit
   `reason="<alt> -> <neu>"`. Fail-closed bei unbekannter `task_id` oder
   ungültigem Prioritätswert (Store wirft `StoreError`, keine stille
   Ablehnung).

5. **Neuer CLI-Befehl `bridge task set-priority <id> <LOW|MEDIUM|HIGH>`**
   (`src/bridge/cli.py`, neuer Subparser unter `task`, analog `set-status`):
   `--actor` Pflicht (gleiches Muster wie andere zustandsverändernde
   Befehle), ruft die neue Store-Methode aus Schritt 4 auf. Kein
   `--commit`-Flag in dieser ersten Version nötig, kann aber analog zu
   anderen `task`-Unterbefehlen ergänzt werden, wenn das Muster aus
   BRIDGE-025 (`gitops.py`-Whitelist) das ohne Zusatzaufwand hergibt —
   nicht erzwingen, wenn es den Auftrag unnötig aufbläht.

6. **Web-UI-Zuweisung** (`src/bridge/webui.py`): neuer schreibender
   Endpunkt `POST /api/task/<id>/priority`, gleiches Sicherheitsmuster wie
   die bestehenden drei Aktions-Endpunkte (`confirm: true` + nicht-leerer
   `actor` Pflicht, Same-Origin-Prüfung, `SECURITY-MODEL.md` Abschnitt 5a
   unverändert einhalten). Ruft **dieselbe** Store-Methode wie die CLI auf
   (kein Parallel-Code, wie bei `copied`/`archive`/`finish`). In der
   Board-/Übersichts-Tabelle: ein einfaches Auswahlfeld (`<select>`,
   `LOW`/`MEDIUM`/`HIGH`) pro Zeile, das bei Änderung die Aktion auslöst —
   kein separater Freigabedialog nötig, da das keine kritische Git-Aktion
   ist (nur Store-Feld), aber `confirm`+`actor` bleiben serverseitig
   trotzdem Pflicht (konsistent mit den bestehenden Endpunkten, keine
   Sonderregel nur für diesen einen einführen).

7. **Sortierung in `_overview_rows`:** `priority`-Wert pro Auftrag lesen
   (Default `MEDIUM`, falls Feld im Dokument fehlt — Altbestand ohne
   Migration muss weiterlaufen). Sortierschlüssel um Prioritäts-Rang
   erweitern: `(0 falls aktiv sonst 1, Prioritaets_Rang[HIGH=0,
   MEDIUM=1, LOW=2], -Zeitstempel)`. Spalte „Priorität" in
   `_overview_text`/Web-UI-Tabelle ergänzen.

8. **Sortierung in `_board_rows`:** wie unter „Kontext" Punkt 4 als
   Annahme benannt — `(Prioritaets_Rang, bridge_task_id)` statt nur
   `bridge_task_id`. Spalte „Priorität" auch hier ergänzen.

9. Tests (`tests/test_cli.py`/`tests/test_store.py`/`tests/test_webui.py`,
   neue Fälle):
   - Schema akzeptiert `priority: HIGH/MEDIUM/LOW`, lehnt ungültige Werte
     ab (fail-closed).
   - Bestehende `task.yaml`-Dokumente ohne `priority`-Feld bleiben valide
     (Default `MEDIUM`).
   - `bridge task set-priority` ändert das Feld, schreibt einen
     `PRIORITY_CHANGED`-Audit-Eintrag mit lesbarem `reason`.
   - Ungültiger Prioritätswert über CLI/Web-UI wird abgelehnt, kein
     stilles Ignorieren.
   - `_overview_rows`: höhere Priorität sortiert innerhalb derselben
     Aktiv/Inaktiv-Gruppe vor niedrigerer Priorität, Zeit bleibt
     Tie-Breaker bei gleicher Priorität.
   - `_board_rows`: höhere Priorität sortiert vor niedrigerer (neue
     Annahme aus Punkt 4/8), `bridge_task_id` bleibt Tie-Breaker.
   - Web-UI-Endpunkt: fehlendes `confirm`/`actor` → HTTP 400 (bestehendes
     Muster), erfolgreicher Aufruf ändert den Store-Zustand identisch zum
     CLI-Pfad.
   - Bestehende Tests (alle Module) weiterhin grün.

10. `docs/CCB-STEUERCHAT-REFERENZ.md` Teil 1 (Schema-Abschnitt), Teil 3
    (CLI-Referenz-Tabelle `task`) und Teil 4 (Web-UI-Referenz) um das neue
    Feld, den neuen Befehl und den neuen Endpunkt ergänzen — Referenz ist
    sonst veraltet.

11. Pflicht-Footer + Abschluss, `--commit` nutzen (BRIDGE-025), **sofort
    pushen** nach jedem Commit (nicht sammeln, siehe verschärfte Regel):
    ```
    bridge run finish BRIDGE-0028 --status COMPLETED --actor claude-code \
      --commit \
      --summary "Neues optionales Feld 'priority' (LOW/MEDIUM/HIGH, Default MEDIUM) in task.schema.yaml, neuer Audit-event_type PRIORITY_CHANGED, neue Store-Methode + CLI-Befehl 'bridge task set-priority', neuer Web-UI-Endpunkt fuer manuelle Zuweisung, Prioritaet als Zusatzkriterium in der Overview-Sortierung (innerhalb Aktiv/Inaktiv-Gruppe) und im Board (vor bridge_task_id). Kein Eingriff in state-model.yaml."
    git push
    ```
    `Auftrag: BRIDGE-0028 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [ ] `priority`-Feld in `schemas/task.schema.yaml`: Enum `LOW`/`MEDIUM`/
      `HIGH`, Default `MEDIUM`, bestehende `task.yaml`-Dokumente ohne das
      Feld bleiben valide.
- [ ] `PRIORITY_CHANGED` in `schemas/audit-event.schema.yaml`
      `event_type`-Enum ergänzt, kein Eingriff in `old_state`/`new_state`.
- [ ] Neue `Store`-Methode für Prioritätswechsel, unabhängig von
      `state_machine`/`set_status`, fail-closed bei ungültigem Wert.
- [ ] `bridge task set-priority <id> <LOW|MEDIUM|HIGH> --actor <n>`
      funktioniert, schreibt Audit-Eintrag.
- [ ] Web-UI: neuer Endpunkt für manuelle Prioritäts-Zuweisung, gleiches
      Sicherheitsmuster (`confirm`+`actor`+Same-Origin) wie bestehende
      Aktions-Endpunkte, ruft dieselbe Store-Methode wie die CLI.
- [ ] `_overview_rows`: Priorität als Zusatzkriterium **innerhalb** der
      bestehenden Aktiv/Inaktiv-Gruppierung, Zeit bleibt finaler
      Tie-Breaker.
- [ ] `_board_rows`: Priorität vor `bridge_task_id` als Sortierkriterium
      (Annahme aus Kontext Punkt 4, ggf. vor Abschluss mit dir bestätigen).
- [ ] Prioritäts-Spalte in CLI-Textausgabe (`overview`, `board`) und
      Web-UI-Tabellen sichtbar.
- [ ] `CCB-STEUERCHAT-REFERENZ.md` aktualisiert (Schema, CLI, Web-UI).
- [ ] Kein Eingriff in `schemas/state-model.yaml`.
- [ ] Bestehende Tests weiterhin grün, neue Tests grün, frischer Klon
      verifiziert.
- [ ] Jeder Commit sofort gepusht, nicht gesammelt (verschärfte Regel).
