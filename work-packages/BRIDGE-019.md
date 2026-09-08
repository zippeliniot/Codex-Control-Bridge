# BRIDGE-019 — Mehrfach-Steuerung: Task-Override für executor/controller, Führungs-/Prüfrollen, Remote-Repo-Feld

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0019 |
| project_id | codex-control-bridge |
| task_class | ARCHITECTURE |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe MEDIUM (Schemaerweiterung + Resolutionslogik + Board-Anpassung nach bereits etabliertem Muster, kein neues Architekturkonzept) |

## Kontext

Hintergrund: CCB soll künftig mit mehreren parallelen Steuer-/Ausführungsakteuren
arbeiten (Claude im Browser + Claude Code, ChatGPT + Codex), und Projekte werden
in der Praxis manchmal gegenseitig zu Kontrollzwecken geprüft (eine KI führt,
eine unterstützt/prüft). Drei konkrete Lücken wurden dabei identifiziert:

1. `executor`/`controller` sind bisher reine **Projekt**-Felder
   (`project.schema.yaml`). Das reicht nicht, wenn innerhalb *eines* Projekts
   mal Claude Code, mal Codex zum Zug kommen soll, oder wenn ein einzelner
   Kontroll-Auftrag ausdrücklich von der jeweils anderen KI geführt werden
   soll, ohne das Projektprofil dauerhaft zu ändern.
2. Es gibt kein Feld, das ausdrückt, welche KI bei einem Auftrag/Projekt die
   **fachliche Führung** hat und welche nur **unterstützend prüft**
   (Cross-Check). Ohne sichtbare Kennzeichnung im Board besteht
   Verwechslungsgefahr, welche KI gerade in welcher Rolle handelt.
3. Ein Steuerprozess ohne lokalen Checkout (z. B. ChatGPT über einen
   GitHub-Connector) kann ein Projekt aktuell nicht zuverlässig einem
   GitHub-Repo zuordnen: `repository` in `project.yaml` ist nur der lokale
   Verzeichnisname (`<basis>/<repository>`, siehe `registry.py`), kein
   `Besitzer/Repo`-Slug für die GitHub-API.

**Wichtig, damit nichts falsch verstanden wird:** Dieses Paket schaltet
**keinen** echten Codex- oder ChatGPT-Livebetrieb scharf. Das
CCB-Projektprofil selbst bleibt `executor: claude-code` /
`controller: human`. Dieses Paket liefert ausschließlich die
**Infrastruktur** (Schema, Resolutionslogik, Anzeige, Dokumentation), damit
einzelne Aufträge/Projekte diese Rollen später bewusst und sichtbar
übernehmen können. Die tatsächliche Aktivierung eines Codex-Executors setzt
voraus, dass zuvor eine eigene, von Dorfschaft getrennte Codex-Umgebung
(eigener Checkout, eigenes `.venv`, eigene Git-Identität) eingerichtet und
ein eng begrenzter Schreibtest durchgeführt wurde — das ist bewusst NICHT
Teil dieses Pakets, sondern folgt separat.

**Bereits vorhanden, kein neues Feld nötig (zur Kenntnis, spart Rückfragen):**
Die granulare Git-Rechtevergabe, die für einen Connector-gesteuerten Akteur
wie ChatGPT wichtig ist (getrennte Freigabe für Stage/Commit/Push/PR/Merge/
Force-Push), existiert bereits vollständig im `permissions`-Feld des
Task-Schemas (`GIT_STAGE, GIT_COMMIT, GIT_PUSH, PR_CREATE, MERGE, DEPLOY,
DATABASE_WRITE, FORCE_PUSH`). Hier ist keine Erweiterung nötig — nur in
`CONTROL.md` (siehe unten) explizit dokumentieren, dass ein
Connector-gesteuerter Akteur einen möglichst engen `permissions`-Auszug pro
Auftrag bekommen soll (z. B. `PR_CREATE` statt direkt `GIT_PUSH`), nicht
automatisch die volle Liste.

## Von Claude Code umzusetzen

### 1) Auftrag anlegen und starten

```
bridge task create tasks/incoming/BRIDGE-0019.yaml
bridge run start BRIDGE-0019 --actor claude-code
```
(Staging-Datei danach löschen, wie in Abschnitt 6 der Übergabe beschrieben.)

### 2) `project.schema.yaml` erweitern

Zwei neue, optionale, nullable Felder ergänzen (additive — bestehende
Profile ohne diese Felder müssen weiterhin gültig bleiben):

```yaml
  review_roles:
    description: >-
      Fachliche Führungs-/Pruefrolle (Kontrollzweck), getrennt von
      executor/controller (die regeln nur die technische Ausfuehrung/
      Steuerung, nicht die fachliche Verantwortung). Projekt-Default;
      kann pro Auftrag ueberschrieben werden (siehe task.schema.yaml).
    type: ["object", "null"]
    additionalProperties: false
    default: null
    properties:
      lead:
        description: "Fachlich fuehrende KI fuer dieses Projekt."
        type: ["string", "null"]
        enum: [anthropic, openai, human, null]
      support:
        description: "Unterstuetzende/pruefende KI (Cross-Check, keine Alleinverantwortung)."
        type: ["string", "null"]
        enum: [anthropic, openai, human, null]

  github_repo:
    description: >-
      Vollqualifizierter GitHub-Slug ("Besitzer/Repo") fuer Steuerprozesse
      ohne lokalen Checkout (z. B. ChatGPT ueber GitHub-Connector/-API).
      Getrennt vom Feld 'repository', das nur der lokale Verzeichnisname
      ist (siehe registry.py: <basis>/<repository>). Null = kein
      dokumentierter Remote-Zugriff ohne lokalen Checkout vorgesehen.
    type: ["string", "null"]
    pattern: "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
    default: null
```

`projects/codex-control-bridge/project.yaml` konkret ergänzen:
```yaml
github_repo: zippeliniot/Codex-Control-Bridge
```
(`review_roles` für das CCB-Projekt selbst bewusst `null` lassen — es gibt
aktuell keine Führungs-/Prüf-Rollentrennung für die Bridge-Entwicklung
selbst, nur für Fremdprojekte wie Dorfschaft/BESS, die das später in ihren
eigenen `project.yaml` setzen.)

### 3) `task.schema.yaml` erweitern

Drei neue, optionale, nullable Felder — Muster identisch zu `model`/
`reasoning_level` (Task-Parameter, keine Bridge-Entscheidung, `null` =
vom Projektprofil erben):

```yaml
  executor:
    description: >-
      Auftragsspezifischer Override der Ausfuehrungsinstanz. Null = vom
      Projektprofil erben (project.schema.yaml: executor).
    type: ["string", "null"]
    enum: [codex, claude-code, null]
    default: null

  controller:
    description: >-
      Auftragsspezifischer Override der Steuerinstanz. Null = vom
      Projektprofil erben (project.schema.yaml: controller).
    type: ["string", "null"]
    enum: [anthropic, openai, human, null]
    default: null

  review_roles:
    description: >-
      Auftragsspezifischer Override der Fuehrungs-/Pruefrolle. Null = vom
      Projektprofil erben (project.schema.yaml: review_roles). Bei
      Nicht-Null vollstaendig (lead + support), kein Teil-Override.
    type: ["object", "null"]
    additionalProperties: false
    default: null
    properties:
      lead:
        type: ["string", "null"]
        enum: [anthropic, openai, human, null]
      support:
        type: ["string", "null"]
        enum: [anthropic, openai, human, null]
```

### 4) Resolutionslogik (neue Funktionen, z. B. in `src/bridge/profiles.py`)

```
resolve_executor(profile, task) -> str | None
resolve_controller(profile, task) -> str | None
resolve_review_roles(profile, task) -> dict | None   # {"lead": ..., "support": ...} oder None
```

Regel: Task-Wert gewinnt, wenn nicht `null`; sonst Projekt-Default; sonst
`None`. Bei `review_roles` gilt der Task-Wert nur als Ganzes (kein Mischen
von Task-`lead` mit Projekt-`support`) — Klarheit vor Flexibilität.

Unittests für alle drei Funktionen: Task-Override, Projekt-Default,
beide `null`, sowie den Sonderfall "Task setzt `review_roles`, Projekt hat
keins" und umgekehrt.

### 5) Board erweitern (`src/bridge/cli.py`)

Neue Funktion `_board_review_roles(store, task)` analog zu
`_board_project()` — nutzt `resolve_review_roles()`, fail-soft auf
`"?"` bei fehlendem/ungültigem Profil (gleiches Muster wie
`_board_project`).

`_board_rows()`/`_board_text()` um eine Spalte **"Führung/Prüfung"**
erweitern, direkt nach der Projekt-Spalte. Format-Vorschlag:

```
Lead: OpenAI · Support: Anthropic
Lead: Anthropic (kein Support)
(keine Rollentrennung)
```

Bestehende Spaltenbreiten in `_board_text()` entsprechend anpassen, damit
die Tabelle lesbar bleibt. Kein `--watch`-Verhalten ändern, nur die
Datenquelle/Darstellung erweitern.

### 6) `CONTROL.md` (neu, Repo-Root, neben `CLAUDE.md`)

Pendant zu `CLAUDE.md`, aber für einen ChatGPT-gesteuerten Steuerprozess
(nicht Claude Code). Muss enthalten:

- Rollenmodell: `controller_actor: chatgpt-control` /
  `executor_actor: codex-executor` als Namenskonvention für die
  bestehenden Felder `actor` (Audit-Event) und `created_by`
  (Task/Result) — keine neuen Felder, nur Konvention.
- Klarstellung: **aktuell nur lesend vorgesehen.** Kein automatischer
  Schreibzugriff ist freigegeben, unabhängig davon, was der
  GitHub-Connector technisch zuließe. Jede Schreibaktion braucht ein
  explizit im Auftrag gelistetes `permissions`-Recht (siehe Abschnitt
  "Bereits vorhanden" oben) und vorherige Freigabe durch den Menschen.
- Bootstrap-Checkliste für einen neuen ChatGPT-Steuerchat (deckt sich mit
  den in der Analyse genannten Anforderungen): aktuelles Projektprofil
  (`projects/<id>/project.yaml`), `github_repo`+`default_branch` als
  Ersatz für einen lokalen Checkout, aktuelle Task-Datei, State/Audit-Spur,
  Ergebnisse/Checkpoints, dieses Dokument selbst.
- Hinweis: ein einzelner Chatverlauf ist NIEMALS alleinige SSOT — SSOT ist
  ausschließlich das Repo (deckt sich mit Abschnitt 4 der Guardrails).
- Kurzer Verweis auf `bridge commands`/`bridge board` als Einstiegspunkte.

`CLAUDE.md` um einen kurzen Verweis ergänzen ("Für einen ChatGPT-gesteuerten
Prozess siehe `CONTROL.md`"), damit beide Dokumente sich gegenseitig finden
— keine inhaltliche Änderung an `CLAUDE.md` sonst.

### 7) Tests

- Schema-Validierung: gültige/ungültige Task-/Projekt-Dokumente mit den
  drei neuen Feldern (inkl. falscher Enum-Werte, fail-closed).
- Resolutionslogik: siehe Punkt 4.
- Board-Rendering: neue Spalte erscheint korrekt, fail-soft-Fall
  (Projekt ohne Profil) bleibt `"?"`.
- Regressionstest: alle bisherigen Fixtures (ohne die neuen Felder) müssen
  weiterhin ohne Änderung gültig sein — die neuen Felder sind additiv und
  `null`-Default, keine mechanische Fixture-Anpassung wie bei BRIDGE-015
  nötig. Falls doch etwas bricht: das ist ein Signal, dass etwas nicht
  additiv genug gebaut wurde — bitte melden statt Fixtures pauschal
  anzupassen.

### 8) Pflicht-Footer

`Auftrag: BRIDGE-0019 / Lauf: RUN-yy / Status: ...`

## Akzeptanzkriterien

- `project.schema.yaml`: `review_roles` (lead/support) und `github_repo`
  neu, beide optional/nullable, additiv (bestehende Profile bleiben ohne
  Änderung gültig).
- `task.schema.yaml`: `executor`, `controller`, `review_roles` neu, alle
  optional/nullable, Override-Semantik wie `model`/`reasoning_level`.
- `projects/codex-control-bridge/project.yaml`: `github_repo:
  zippeliniot/Codex-Control-Bridge` ergänzt.
- Resolutionsfunktionen liefern korrekt Task-Override vor Projekt-Default
  vor `None`, mit Unittests für alle Kombinationen.
- `bridge board` zeigt eine neue Spalte "Führung/Prüfung" mit aufgelöstem
  Lead/Support pro Zeile; leerer/nicht gesetzter Fall klar erkennbar
  (nicht leer/verwechselbar mit einem echten Wert).
- `CONTROL.md` neu im Repo-Root, `CLAUDE.md` verweist darauf.
- Kein bestehendes Verhalten von `bridge task create` / `run start` /
  `run finish` / `task copied` / `task archive` ändert sich.
- Alle Tests grün (bestehende 151 + neue), frischer Klon verifiziert.
- Keine Aktivierung von `executor: codex` oder `controller: openai` im
  CCB-Projektprofil selbst — bleibt `claude-code`/`human`.
