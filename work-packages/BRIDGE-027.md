# BRIDGE-027 — Orchestrator-Grundbaustein 1: orchestrator_policy + Entscheidungen dokumentiert

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0027 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| review_roles | lead: anthropic, support: openai (aus Projektprofil übernommen) |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM — reine Schema-/Doku-Erweiterung, kein Eingriff in Zustandsmaschine oder Laufzeitlogik. |

> **Verbindlich für diesen und jeden CCB-Auftrag:**
> - Jede Zustandsänderung läuft über die Bridge-CLI, kein direktes Bearbeiten
>   von Store-Dateien.
> - `GIT_PUSH` steht im Profil — nach `run finish` **muss** gepusht werden,
>   über `--commit` (BRIDGE-025), und **sofort**, nicht gesammelt.

## Kontext

Im Steuerchat wurden zu `docs/CCB-ORCHESTRATOR-KONZEPT.md` (drei offene Fragen)
folgende Entscheidungen getroffen — dieser Auftrag ist der erste von fünf
geplanten Bausteinen, die daraus folgen:

**Frage 1 (Grenze automatisch/Vorschlag):** projektabhängig statt global —
jedes Projekt bekommt ein eigenes `orchestrator_policy`-Feld, das festlegt,
welche Permission-Typen für dieses Projekt automatisch ausgelöst werden
dürfen. `FORCE_PUSH` bleibt dabei kategorisch ausgeschlossen (bestehende,
nicht verhandelbare Leitplanke aus BRIDGE-024) — das ist keine neue
Design-Entscheidung dieses Auftrags, sondern die konsequente Fortführung
einer bereits bestehenden.

**Frage 2 (Priorität):** Stufen `LOW`/`MEDIUM`/`HIGH` (kein `URGENT`),
Default `MEDIUM`, **manuell** über das Web-GUI zugewiesen. Braucht einen
neuen Befehl `bridge task set-priority` (eigener, späterer Auftrag,
BRIDGE-028 — **nicht** Teil dieses Auftrags).

**Frage 3 (Web-UI als Trägerprozess):** Web-UI soll zur zentralen
Mehrmaschinen-/Mehrprojekt-Steuerung ausgebaut werden. Daraus zwei konkrete
Folgeentscheidungen:
- Der CCB-Store (`audit/audit.jsonl` u. a.) ist projektübergreifend
  gemeinsam in einem Repo — bei gleichzeitigen Commits aus mehreren
  Projekten/Maschinen kann `git push` an Non-Fast-Forward scheitern.
  Lösung: automatisches `git pull --rebase` + Retry bei Push-Fehlschlag,
  nie `--force` (eigener, späterer Auftrag, BRIDGE-029 — **nicht** Teil
  dieses Auftrags).
- Support-KI-Prüfaufträge bekommen eine sichtbare Unternummer
  (`BRIDGE-0027-R1` usw., Schema-Pattern-Erweiterung), `task_class:
  READONLY_CHECK`, technisch auf reine Leserechte beschränkt (eigener,
  späterer Auftrag, BRIDGE-030 — **nicht** Teil dieses Auftrags).

**Geplante Reihenfolge (Roadmap, zur Doku, kein Auftrags-Auto-Start):**
- BRIDGE-0027 (dieser Auftrag): `orchestrator_policy`-Feld + Doku der
  Entscheidungen.
- BRIDGE-0028: Prioritätsfeld (`priority` in `task.schema.yaml`) +
  `task set-priority` CLI-Befehl + Web-UI-Zuweisung + Sortierung nach
  Priorität in Board/Overview.
- BRIDGE-0029: Git-Push-Retry-Mechanik (`pull --rebase` + Retry) in
  `gitops.py`.
- BRIDGE-0030: Review-Unternummern-Pattern (`-R<n>`-Suffix in
  `bridge_task_id`/`depends_on`) + technische Durchsetzung von
  `review_roles.support` als reine Leserolle.
- BRIDGE-0031 (erst nach 0027–0030 fertig): die eigentliche
  Orchestrator-Auslöselogik selbst, aufbauend auf `orchestrator_policy` +
  `priority`.

**Bewusst nicht in diesem Auftrag:** keine der vier oben genannten späteren
Fähigkeiten, kein neuer Zustand in `schemas/state-model.yaml`, keine
Änderung an `task.schema.yaml`.

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0027.yaml
   bridge run start BRIDGE-0027 --actor claude-code
   ```

2. **`schemas/project.schema.yaml` erweitern** — neues optionales Feld
   `orchestrator_policy`, strukturell an `review_roles` angelehnt (siehe
   dortiges Muster: `type: ["object", "null"]`, `additionalProperties:
   false`, `default: null`):
   ```yaml
   orchestrator_policy:
     description: >-
       Projektspezifische Grenze fuer automatisches Ausloesen durch einen
       kuenftigen Orchestrator-Prozess (BRIDGE-0031). Alles ausserhalb von
       auto_trigger_permissions bleibt Vorschlag/Mensch-Aktion.
     type: ["object", "null"]
     additionalProperties: false
     default: null
     properties:
       auto_trigger_permissions:
         description: >-
           Permission-Typen, die fuer dieses Projekt automatisch ausgeloest
           werden duerfen. FORCE_PUSH ist hier bewusst nicht im Enum (siehe
           BRIDGE-024 Sicherheitsentscheid, keine Ausnahme moeglich).
         type: array
         items:
           type: string
           enum: [READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION, GIT_STAGE,
                  GIT_COMMIT, GIT_PUSH, PR_CREATE, MERGE, DEPLOY,
                  DATABASE_WRITE]
         default: [READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION]
   ```
   Exaktes Feld-Layout nach eigenem Ermessen an bestehenden Schema-Stil
   anpassen (Kommentare, Reihenfolge), aber: `FORCE_PUSH` darf in keinem
   Fall im Enum auftauchen — das ist keine Verhandlungssache.

3. **Bestehende sieben `project.yaml` NICHT anfassen** — Feld ist optional
   mit `default: null`, alle bestehenden Profile bleiben ohne Änderung
   gültig. Nicht von sich aus Beispielwerte eintragen, das ist eine
   projektindividuelle Entscheidung für später.

4. **`docs/CCB-ORCHESTRATOR-KONZEPT.md` aktualisieren:**
   - Die drei ursprünglich offenen Fragen durch die im Kontext-Abschnitt
     oben zusammengefassten Entscheidungen ersetzen/ergänzen (nicht
     einfach den Kontext-Abschnitt hier hineinkopieren, sondern sachlich
     ins bestehende Dokumentformat einfügen).
   - Roadmap-Abschnitt mit BRIDGE-0027 bis BRIDGE-0031 wie oben aufführen.

5. Tests (`tests/test_profiles.py` oder wo `review_roles`-Validierung
   bereits getestet wird — bestehende Testdatei wiederverwenden, keine
   neue Datei ohne Grund):
   - `orchestrator_policy: null` validiert.
   - `orchestrator_policy` mit `auto_trigger_permissions: [READ_ONLY]`
     validiert.
   - `orchestrator_policy` mit `auto_trigger_permissions` enthält
     `FORCE_PUSH` → Schema lehnt ab (negative Testfall, das ist der
     wichtigste Test in diesem Auftrag).
   - Bestehende sieben `project.yaml` weiterhin gültig ohne Änderung.

6. Pflicht-Footer + Abschluss, `--commit` nutzen, **sofort pushen**:
   ```
   bridge run finish BRIDGE-0027 --status COMPLETED --actor claude-code \
     --commit \
     --summary "orchestrator_policy Projektfeld in project.schema.yaml (analog review_roles, FORCE_PUSH kategorisch ausgeschlossen), CCB-ORCHESTRATOR-KONZEPT.md um Entscheidungen aus Steuerchat + Roadmap BRIDGE-0027..0031 ergaenzt, bestehende Projektprofile unveraendert gueltig."
   git push
   ```
   `Auftrag: BRIDGE-0027 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [ ] `orchestrator_policy` in `schemas/project.schema.yaml`, strukturell
      wie `review_roles` (Objekt, `additionalProperties: false`,
      `default: null`).
- [ ] `auto_trigger_permissions` mit Enum aus bestehenden Permission-Werten,
      `FORCE_PUSH` **nicht** im Enum.
- [ ] Default `[READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION]`, wenn
      `orchestrator_policy` gesetzt, aber `auto_trigger_permissions` fehlt.
- [ ] Alle sieben bestehenden `project.yaml` weiterhin gültig, unverändert.
- [ ] Negativer Testfall: `FORCE_PUSH` in `auto_trigger_permissions` wird
      vom Schema abgelehnt.
- [ ] `docs/CCB-ORCHESTRATOR-KONZEPT.md` enthält die drei Entscheidungen +
      Roadmap BRIDGE-0027–0031.
- [ ] Kein Eingriff in `schemas/state-model.yaml` oder `task.schema.yaml`.
- [ ] Keine neuen CLI-Befehle, keine Auslöselogik in diesem Auftrag.
- [ ] Bestehende Tests weiterhin grün, neue Tests grün, frischer Klon
      verifiziert.
- [ ] Jeder Commit sofort gepusht, nicht gesammelt.
