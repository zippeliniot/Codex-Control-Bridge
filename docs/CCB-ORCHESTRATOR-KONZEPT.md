# CCB — Konzept: Orchestrator (Reihenfolge-/Ausführungsautomatik)

**Status: Schema-Grundbaustein implementiert (BRIDGE-0027 abgeschlossen).** Die
eigentliche Auslöselogik folgt in BRIDGE-0031, sobald die Bausteine 0028–0030
fertig sind. Kein Code für den Orchestrator-Auslöser in diesem Dokument.

## Ausgangslage (aus der Steuerchat-Sitzung, 12.09.2026)

Bei mehreren parallel laufenden Projekten auf zwei Maschinen soll die Bridge
nicht nur anzeigen, was passiert (BRIDGE-0026), sondern auch:

1. Vorschlagen und/oder auslösen, was als Nächstes gemacht werden soll —
   **„beides, je nach Auftragsart"**.
2. Bei mehreren gleichzeitig bereiten Aufträgen anhand von
   **Priorität/Dringlichkeit** (neues Feld) entscheiden, was zuerst kommt —
   zusätzlich zu `depends_on` (bereits vorhanden).
3. **In der Web-UI** laufen, auf Basis von BRIDGE-023/024.

## Getroffene Entscheidungen (Steuerchat, 12.09.2026)

### Frage 1: Grenze „Vorschlag" vs. „automatischer Auslöser" — projektabhängig

Die Grenze ist **nicht global**, sondern **pro Projekt einstellbar**: Jedes
Projekt bekommt ein eigenes `orchestrator_policy`-Feld in `project.yaml`
(`schemas/project.schema.yaml`), das festlegt, welche Permission-Typen für
dieses Projekt automatisch ausgelöst werden dürfen.

- **`FORCE_PUSH` bleibt kategorisch ausgeschlossen** — nicht konfigurierbar,
  nicht verhandelbar (bestehende Leitplanke aus BRIDGE-024, Sicherheitsmodell
  Abschnitt 3). Das Feld `auto_trigger_permissions` enthält `FORCE_PUSH`
  bewusst nicht im Enum.
- Alle anderen Permission-Typen (inkl. `GIT_PUSH`, `MERGE`, `DEPLOY`,
  `DATABASE_WRITE`, `PR_CREATE`) können projektindividuell freigegeben werden —
  der **Default** ist konservativ: `[READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION]`.
- Schema-Feld ist optional mit `default: null` → alle bestehenden
  Projektprofile bleiben ohne Änderung gültig.

Implementiert in BRIDGE-0027 (dieses Dokument).

### Frage 2: Priorität — Stufen LOW/MEDIUM/HIGH, manuelle Zuweisung

- **Stufen:** `LOW` / `MEDIUM` / `HIGH` (kein `URGENT` — einfach halten,
  analog zur bestehenden `reasoning_level`-Konvention).
- **Default:** `MEDIUM`.
- **Zuweisung:** manuell über das Web-GUI (nicht automatisch abgeleitet aus
  Alter oder `depends_on`-Tiefe).
- **CLI-Befehl:** `bridge task set-priority` — eigener, späterer Auftrag
  (**BRIDGE-0028**, nicht Teil dieses Auftrags).

### Frage 3: Web-UI als Trägerprozess — zentrale Mehrmaschinen-Steuerung

Die Web-UI (`http://127.0.0.1:8420`) soll zur zentralen Mehrmaschinen-/
Mehrprojekt-Steuerung ausgebaut werden. Zwei konkrete Folgeentscheidungen:

**Push-Retry (BRIDGE-0029):** Der CCB-Store (`audit/audit.jsonl` u. a.) ist
projektübergreifend gemeinsam in einem Repo. Bei gleichzeitigen Commits aus
mehreren Projekten/Maschinen kann `git push` an Non-Fast-Forward scheitern.
Lösung: automatisches `git pull --rebase` + Retry bei Push-Fehlschlag — nie
`--force`. Eigener Auftrag **BRIDGE-0029**, nicht Teil dieses Auftrags.

**Review-Unternummern (BRIDGE-0030):** Support-KI-Prüfaufträge bekommen eine
sichtbare Unternummer (`BRIDGE-0027-R1` usw., Schema-Pattern-Erweiterung),
`task_class: READONLY_CHECK`, technisch auf reine Leserechte beschränkt.
Eigener Auftrag **BRIDGE-0030**, nicht Teil dieses Auftrags.

**Laufzeit-Einschränkung bleibt:** Die Web-UI läuft nur, solange jemand
`webui serve` gestartet hat — kein 24/7-Betrieb ohne offenes Browserfenster,
kein Hintergrunddienst. Bewusst gewählt (nicht `watch loop`).

## Roadmap (Umsetzungsreihenfolge, kein Auto-Start)

| Auftrag | Inhalt | Zustand |
|---------|--------|---------|
| **BRIDGE-0027** | `orchestrator_policy`-Feld in `project.schema.yaml` + diese Entscheidungen dokumentiert | **abgeschlossen** |
| **BRIDGE-0028** | Prioritätsfeld (`priority` in `task.schema.yaml`) + `bridge task set-priority` + Web-UI-Zuweisung + Sortierung nach Priorität in Board/Overview | geplant |
| **BRIDGE-0029** | Git-Push-Retry (`pull --rebase` + Retry) in `gitops.py` | geplant |
| **BRIDGE-0030** | Review-Unternummern-Pattern (`-R<n>`-Suffix) + technische Durchsetzung `review_roles.support` als Leserrolle | geplant |
| **BRIDGE-0031** | Eigentliche Orchestrator-Auslöselogik, aufbauend auf `orchestrator_policy` + `priority` (erst nach 0027–0030 fertig) | geplant |

## Vorgeschlagener grober Aufbau (zur Implementierung, BRIDGE-0031)

1. `task.schema.yaml`: neues optionales Feld `priority` (Enum LOW/MEDIUM/HIGH,
   Default `MEDIUM`), rückwärtskompatibel — **BRIDGE-0028**.
2. `project.yaml`-Erweiterung: `orchestrator_policy` — bereits implementiert
   (BRIDGE-0027), pro Projekt konfigurierbar.
3. Neue Funktion (aufbauend auf `bridge overview` aus BRIDGE-0026): aus
   allen „bereiten" Aufträgen (Abhängigkeiten erfüllt) den nächsten nach
   Priorität auswählen — **BRIDGE-0031**.
4. Je nach Berechtigungsprofil (`orchestrator_policy.auto_trigger_permissions`):
   Button „Vorschlag anzeigen" vs. automatischer Trigger-Aufruf der Bridge-CLI
   aus der Web-UI heraus (technisch: `subprocess`-Mechanismus analog
   `gitops.py`, aber für `bridge run start` — neue Whitelist-Logik,
   bestehende nicht wiederverwenden) — **BRIDGE-0031**.

## Nicht Teil dieses Konzepts (bewusst abgegrenzt)

- Kein `watch loop`-Dauerprozess (explizit nicht gewählt).
- Keine Änderung an `schemas/state-model.yaml` — der Orchestrator schlägt
  vor/löst aus, erfindet aber keine neuen Zustände.
- Keine Maschinen-Kapazitätssperre — zwei Aufträge dürfen bewusst gleichzeitig
  auf derselben Maschine „bereit" sein; Reihenfolge ist eine
  Anzeige-/Empfehlungsfrage, keine technische Sperre.
