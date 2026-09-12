# CCB — Übergabe an neuen Steuerchat (Stand: 12.09.2026, nach BRIDGE-026/027, vor BRIDGE-028)

Ersetzt `docs/handover/CCB-UEBERGABE-v7.md`. **Abschnitt 0 ist bindend.**
Diese Übergabe ergänzt (ersetzt nicht) `docs/CCB-STEUERCHAT-ARBEITSWEISE.md`
und `docs/CCB-STEUERCHAT-REFERENZ.md` — beide zusätzlich lesen, siehe
Sitzungsstart-Pflichtablauf dort.

## Abschnitt 0 — Was sich seit v7 geändert hat (wichtigste Punkte zuerst)

1. **`BRIDGE-0026` abgeschlossen und archiviert.** Neuer Befehl
   `bridge overview` (CLI + Web-UI-Bereich „Alle Projekte – Gesamtübersicht"):
   zeigt alle Aufträge/Zustände inkl. `RUNNING`/`CLAIMED` (die das normale
   Board bewusst versteckt), Maschine wo bekannt sonst `?`, aktiv vor
   inaktiv sortiert (30-Min.-Schwelle). Bestehende Board-Funktionen
   unverändert. Vollständig verifiziert (frischer Klon, Diff, Tests,
   Funktion selbst aufgerufen).
2. **`BRIDGE-0027` abgeschlossen und archiviert.** Neues optionales Feld
   `orchestrator_policy` in `schemas/project.schema.yaml` (Objekt, analog
   `review_roles`, `default: null`), mit `auto_trigger_permissions`
   (Standard `[READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION]`). **`FORCE_PUSH`
   ist kategorisch nicht im Enum** — nicht verhandelbar, bestehende
   Leitplanke aus BRIDGE-024. Alle sieben bestehenden `project.yaml`
   unverändert gültig. Kein Eingriff in `state-model.yaml`/`task.schema.yaml`/
   `src/bridge/*.py`.
3. **`docs/CCB-ORCHESTRATOR-KONZEPT.md` — alle drei offenen Fragen
   beantwortet** (Steuerchat-Sitzung 12.09.2026), Dokument entsprechend
   aktualisiert:
   - **Frage 1 (Grenze automatisch/Vorschlag):** projektabhängig statt
     global, über `orchestrator_policy` (siehe Punkt 2). Implementiert.
   - **Frage 2 (Priorität):** Stufen `LOW`/`MEDIUM`/`HIGH` (kein `URGENT`),
     Default `MEDIUM`, **manuelle** Zuweisung über das Web-GUI. Noch
     **nicht** implementiert — das ist `BRIDGE-0028`.
   - **Frage 3 (Web-UI als Trägerprozess):** Web-UI wird zur zentralen
     Mehrmaschinen-/Mehrprojekt-Steuerung ausgebaut. Daraus zwei konkrete
     Folgeaufträge: Git-Push-Retry für die projektübergreifend geteilte
     `audit/audit.jsonl` (`BRIDGE-0029`) und ein sichtbares
     Unternummern-Schema (`BRIDGE-0027-R1` usw.) für rein lesende
     Support-KI-Prüfaufträge (`BRIDGE-0030`). Laufzeit-Einschränkung
     bestätigt: Web-UI nur aktiv, solange `webui serve` läuft, kein
     24/7-Automat.
   - **Roadmap festgelegt** (Reihenfolge, kein Auto-Start ohne
     Bestätigung): `BRIDGE-0027` (fertig) → `BRIDGE-0028` (Priorität) →
     `BRIDGE-0029` (Push-Retry) → `BRIDGE-0030` (Review-Unternummern) →
     `BRIDGE-0031` (eigentliche Orchestrator-Auslöselogik, erst nach
     0027–0030).
4. **Qualitätsauffälligkeit bei der `BRIDGE-0027`-Verifikation, im Auge
   behalten:** `changed_files` in `result.yaml` war wieder unvollständig
   (fehlten `audit/audit.jsonl`, `tasks/BRIDGE-0027/task.yaml`,
   `results/.../heartbeat.json` — alle drei tatsächlich im Diff enthalten),
   obwohl `BRIDGE-025` das strukturell beheben sollte. Zusätzlich falsche
   Testzahl im Footer/`result.yaml` (behauptet „38 Tests gesamt",
   tatsächlich 266). Kein inhaltlicher Mangel am Ergebnis selbst (manuell
   gegengeprüft), aber bei jedem künftigen Abschluss weiterhin **nicht**
   auf `changed_files`/Testzahl-Angaben verlassen, immer frisch nachzählen.
   Tritt das Muster ein drittes Mal auf, eigenen kleinen Auftrag daraus
   machen.
5. **Keine Änderung an den sieben Projektprofilen, an GitHub-App-Freigaben
   oder an `executor`/`controller`/`review_roles`** seit v7 — Tabelle unten
   unverändert übernommen.

## Aktueller Stand der sieben Projektprofile

| project_id | executor | controller | review_roles.lead / support | read_only |
|---|---|---|---|---|
| codex-control-bridge | claude-code | human | anthropic / openai | false |
| dorfschaft | codex | openai | openai / anthropic | false |
| bess-msrechner | codex | openai | openai / anthropic | false |
| bess-platform | codex | openai | openai / anthropic | false |
| wetter-app | claude-code | human | anthropic / openai | false |
| climac | claude-code | human | anthropic / openai | false |
| tanken-monitor | claude-code | human | anthropic / openai | false |

## Aktueller Stand (verifiziert per frischem Klon via `bash_tool`, HEAD `fbead77`)

- `BRIDGE-0017` bis `BRIDGE-0027`: alle **`ARCHIVED`**.
- Testsuite-Stand zuletzt verifiziert: **266 Tests grün** (Stand nach
  `BRIDGE-0027`, frisch nachgezählt, nicht aus einer Behauptung
  übernommen).
- Nächste freie ID: **`BRIDGE-0028`** — Prioritätsfeld (`priority` in
  `task.schema.yaml`, `bridge task set-priority`-Befehl, Web-UI-Zuweisung,
  Sortierung nach Priorität in Board/Overview). Work-Package **noch nicht
  erstellt**, laut Roadmap der nächste Schritt.

## Nicht von selbst anfangen bei

- `BRIDGE-0028` starten, ohne vorher das Work-Package mit dem Nutzer
  abzustimmen (Detailfragen zur Sortierlogik/Web-UI-Darstellung sind nicht
  automatisch mitentschieden, nur die drei Grundfragen aus dem
  Orchestrator-Konzept).
- Über die Roadmap-Reihenfolge hinausspringen (z. B. `BRIDGE-0031` vor
  Abschluss von `0028`–`0030` spezifizieren).
- GitHub-App-Repository-Freigabe für die restlichen sechs Repos (nur
  `dorfschaft` bisher bestätigt) — nicht ungefragt erweitern.
- `review_roles`/`executor`/`controller` weiterer Projekte ändern, ohne
  erneute ausdrückliche Angabe wie in vorherigen Sitzungen.

## Offene nächste Schritte (Reihenfolge)

1. Mit dem Nutzer `BRIDGE-0028` (Prioritätsfeld) besprechen/spezifizieren,
   Work-Package + Staging-YAML als Dateien liefern (nicht als
   Chat-Codeblock).
2. Wie gewohnt an Claude Code übergeben, `run finish`-Footer **nicht**
   ungeprüft glauben — volle Vier-Punkte-Prüfung inkl. frischer
   Testzahl-Nachzählung (siehe Punkt 4 oben).
3. Danach in Reihenfolge: `BRIDGE-0029` (Push-Retry), `BRIDGE-0030`
   (Review-Unternummern), erst danach `BRIDGE-0031` (Orchestrator-Logik).
