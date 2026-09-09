# BRIDGE-023 — Web-UI-Verbesserungen (Auto-Refresh-Härtung, persistenter Log, Client-Filter)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0023 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM (drei zusammenhängende Frontend-Erweiterungen an bestehender, getesteter Basis — kein neues Backend-Konzept, aber mehrere Interaktionspfade, die sauber gegeneinander getestet werden müssen). |

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

Aus `BRIDGE-020` RUN-02 im Betrieb sichtbar gewordene Lücken in der Web-UI
(`src/bridge/webui.py`, `_PAGE`-Template):

1. **Auto-Refresh vs. offene Interaktion.** `refresh()` läuft per
   `setInterval(refresh, REFRESH_MS)` (15s) und ersetzt `#board`/`#other`
   per `innerHTML`. Das Actor-Feld wird bereits nur befüllt, wenn es leer
   ist — das bleibt so und wird als Regressionstest abgesichert. Die
   eigentliche Gefahr entsteht erst durch die beiden neuen Features unten:
   ein naiver Refresh würde die Scroll-Position eines Logs oder die
   Eingabewerte/Fokus von Filterfeldern zerstören.
2. **Flash-Meldung statt Log.** `flash()` schreibt aktuell in `#flash` und
   löscht Erfolgsmeldungen nach 6s (`setTimeout`). Fehler bleiben stehen,
   werden aber beim nächsten `post()` überschrieben. Es gibt keine
   Historie — wer nicht im richtigen Moment hinschaut, verpasst, was
   passiert ist.
3. **Kein Filter im Board.** Bei vielen offenen Aufträgen (`other`-Liste)
   gibt es keine Möglichkeit, nach Projekt, Status oder `bridge_task_id`
   einzugrenzen — alle Daten sind bereits im `/api/board`-Payload
   vorhanden (`board`, `other`), es fehlt nur die Client-Logik.

**Bewusst nicht im Scope:** kein neuer Server-Endpoint, keine
Server-seitige Filterung, kein Persistieren des Logs über einen
Seiten-Reload hinaus (reiner In-Memory-Zustand der laufenden Seite reicht
laut Scope-Absprache).

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0023.yaml
   bridge run start BRIDGE-0023 --actor claude-code
   ```
   (Staging-Datei danach löschen.)

2. **Persistenter Aktions-Log** (`src/bridge/webui.py`, `_PAGE`-Template):
   - Neuer Container unterhalb von `#flash` (z. B. `<div id="log">` mit
     `max-height` + `overflow-y: auto`), `#flash` bleibt zusätzlich für die
     unmittelbare Erfolg/Fehler-Rückmeldung erhalten (kein Ersatz, Ergänzung).
   - `post()` hängt bei jedem Ergebnis (Erfolg wie Fehler) einen Eintrag an
     ein In-Memory-Array an: Zeitstempel (lokale Zeit, `toLocaleTimeString()`
     reicht), Aktion (`copied`/`archive`/`finish`), betroffene
     `bridge_task_id`, Ergebnis (`old_state → new_state` bzw. Fehlertext).
   - Rendering des Logs erfolgt **nicht** im 15s-`refresh()`-Zyklus, sondern
     nur beim Anhängen eines neuen Eintrags — der Log-Container darf vom
     Board-Refresh nicht angerührt werden (verhindert automatisch das
     Scroll-Problem aus Kontext-Punkt 1).
   - Neueste Einträge oben (prepend), damit die letzte Aktion ohne Scrollen
     sichtbar ist.

3. **Clientseitige Filter/Suche** (`_PAGE`-Template, `refresh()`):
   - Drei Eingabefelder oberhalb der Tabellen: Projekt (Text), Status
     (Text oder Dropdown mit den in `data.board`/`data.other` tatsächlich
     vorkommenden Werten), `bridge_task_id` (Text, Teilstring-Suche,
     case-insensitive).
   - Filterung passiert **nach** dem Fetch, auf den bereits im Speicher
     liegenden `data.board`/`data.other` — kein neuer Server-Endpoint
     (Scope-Vorgabe).
   - Filterwerte werden in JS-Variablen gehalten (nicht nur im DOM), damit
     `refresh()` bei jedem 15s-Tick den zuletzt aktiven Filter erneut auf
     die frisch geladenen Daten anwendet, statt ihn zu vergessen.
   - Eingabefelder selbst werden vom Refresh **nicht** neu erzeugt/ersetzt
     (nur die Tabellenzeilen `tbody` wie bisher) — Fokus und Cursorposition
     bleiben beim Tippen erhalten, auch wenn währenddessen ein Tick feuert.

4. Tests (`tests/test_webui.py`, neue Testfälle in `WebUiReadTests` bzw.
   neue Klasse `WebUiFrontendTests` je nach sinnvollster Einordnung):
   - Regressionstest: Actor-Feld wird bei nicht-leerem Wert von `refresh()`
     nicht überschrieben (bestehendes Verhalten, jetzt mit Test).
   - Log-Eintrag entsteht bei erfolgreicher wie bei fehlgeschlagener
     Aktion, mit den vier genannten Feldern.
   - Filterfunktion (falls als eigenständige, testbare JS-Funktion
     extrahierbar) reduziert `board`/`other` korrekt nach Projekt, Status,
     `bridge_task_id` — Kombination mehrerer Filter gleichzeitig prüfen.
   - Bestehende Lese-/Aktions-Endpunkttests (`WebUiReadTests`,
     `WebUiActionTests`, `WebUiCliTests`) bleiben unverändert grün.
   - Da reines Frontend-JS in `_PAGE` eingebettet ist: wo sinnvoll testbare
     Funktionen isolieren, statt ungetesteten Inline-Code zu vergrößern;
     wo das den Scope sprengt, mindestens Integrationstest über den echten
     laufenden Server (Muster aus `WebUiBase`) für die drei neuen
     Endpunkt-unabhängigen Verhaltensweisen (Log-Anhängen über wiederholte
     POSTs, Filter-Persistenz über einen simulierten Refresh-Tick).

5. `docs/security/SECURITY-MODEL.md` Abschnitt 5a: nur anfassen, falls sich
   am Sicherheitsverhalten (Same-Origin, Bestätigungspflicht) etwas ändert —
   nach aktuellem Scope nicht der Fall, da alle drei Änderungen reines
   Frontend-Verhalten ohne neue Endpunkte sind.

6. Da dieser Auftrag `GIT_PUSH` im Berechtigungsprofil trägt: Nach
   `run finish` selbst `git push` ausführen (Ask-Bestätigung in Claude Code
   bestätigen). `--force`-Push bleibt in jedem Fall verboten.

7. Pflicht-Footer + Abschluss:
   ```
   bridge run finish BRIDGE-0023 --status COMPLETED --actor claude-code \
     --summary "Web-UI: Auto-Refresh haertet Actor-Feld (Regressionstest), persistenter scrollbarer Aktions-Log ergaenzt #flash statt es zu ersetzen, clientseitige Filter (Projekt/Status/bridge_task_id) ohne neuen Server-Endpoint."
   git push
   ```
   `Auftrag: BRIDGE-0023 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [x] Actor-Feld wird von `refresh()` nicht überschrieben, wenn bereits ein
      Wert eingetragen ist (Regressionstest vorhanden und grün).
      (`WebUiFrontendTests.test_actor_field_not_overwritten_when_filled`)
- [x] Persistenter Aktions-Log zeigt Zeitstempel, Aktion, betroffene
      `bridge_task_id` und Ergebnis für jede ausgeführte Aktion
      (Erfolg **und** Fehler), bleibt über mehrere 15s-Refresh-Ticks hinweg
      sichtbar/gescrollt erhalten, `#flash` bleibt zusätzlich bestehen.
      (`#log` scrollbar, `addLog()` nur in `post()`, nie in `refresh()`;
      `makeLogEntry`-Felder per node getestet.)
- [x] Client-Filter (Projekt, Status, `bridge_task_id`) reduziert Board und
      "Offene Aufträge außerhalb des Boards" korrekt, auch in Kombination.
      (`filterRows`/`rowMatches` per node getestet, inkl. Kombination.)
- [x] Aktiver Filterzustand übersteht einen Auto-Refresh-Tick (wird auf die
      neu geladenen Daten erneut angewendet, nicht zurückgesetzt).
      (`filterState` als JS-Variable, `renderTables()` aus `refresh()`;
      `test_filter_reapplies_to_fresh_data_after_refresh_tick`.)
- [x] Eingabefokus/Cursorposition in Filterfeldern übersteht einen
      Auto-Refresh-Tick während des Tippens. (Inputs sind statisch im HTML,
      `refresh()` schreibt nur `tbody` — `test_refresh_only_touches_tbody...`.)
- [x] Kein neuer Server-Endpoint, kein serverseitiges Filtern (Scope-Vorgabe
      eingehalten, `board_payload()`/HTTP-Routen unverändert).
- [x] Bestehende Tests (`WebUiReadTests`, `WebUiActionTests`,
      `WebUiCliTests`) weiterhin grün.
- [x] Alle Tests grün (bestehende Basis + neue), frischer Klon verifiziert.
      (208 Tests.)
- [ ] Commit gepusht (dieser Auftrag trägt `GIT_PUSH`) — folgt nach `run finish`.
