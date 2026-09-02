# PROJEKTKONZEPT  
# Codex Control Bridge – Automatisierte Auftrags- und Ergebnisübergabe zwischen Steuerchat und Codex

**Projekt-ID:** CCB  
**Arbeitsname:** Codex Control Bridge  
**Status:** KONZEPT / NOCH NICHT IMPLEMENTIERT  
**Erstes Zielsystem:** Dorfschaft  
**Architekturprinzip:** Projektunabhängige Infrastruktur mit projektbezogenen Adaptern  
**Auftragsnummerierung:** BRIDGE-001, BRIDGE-002, BRIDGE-003, …  

---

# 1. Ausgangssituation

Bei komplexen Entwicklungsprojekten wird ChatGPT als übergeordneter Steuer- und Review-Chat verwendet. Codex übernimmt operative Aufgaben in lokalen Arbeitsumgebungen, Worktrees oder Repositories.

Der aktuelle Ablauf ist teilweise manuell:

1. ChatGPT erstellt einen strukturierten Codex-Auftrag.
2. Der Benutzer kopiert diesen Auftrag in Codex.
3. Codex arbeitet den Auftrag ab.
4. Codex erzeugt eine strukturierte Ergebnisausgabe.
5. Der Benutzer kopiert das Ergebnis zurück in den ChatGPT-Steuerchat.
6. ChatGPT bewertet das Ergebnis und erzeugt den Folgeauftrag.

Dieser Ablauf funktioniert, verursacht jedoch vermeidbare manuelle Übergaben und kann bei vielen Arbeitspaketen zu folgenden Problemen führen:

- Copy/Paste-Aufwand
- Verlust längerer Codex-Ergebnisse
- falsche Zuordnung von Ergebnissen zu Aufträgen
- fehlende automatische Erkennung abgeschlossener Aufträge
- Unterbrechungen durch Usage-Limits
- schwierige Wiederaufnahme nach Rechnerwechsel
- Chatwechsel ohne vollständigen Kontext
- fehlende zentrale Maschinen- und Projektunabhängigkeit
- Risiko, dass Ergebnisse nur im Codex-Chat vorhanden sind
- unnötige Wiederholung bereits erledigter Arbeiten

Das Projekt **Codex Control Bridge** soll diese Übergaben standardisieren und schrittweise automatisieren.

---

# 2. Hauptziel

Die Codex Control Bridge soll eine projektunabhängige Vermittlungsschicht zwischen:

**Steuerprozess → Codex → Ergebnis → Steuerprozess**

bereitstellen.

Ein Codex-Auftrag soll eindeutig erfasst, ausgeführt, überwacht, abgeschlossen und dem Steuerprozess wieder zur Verfügung gestellt werden können.

Langfristiges Ziel:

> Ein Codex-Auftrag soll nach Abschluss automatisch erkannt und innerhalb kurzer Zeit als strukturiertes Ergebnis für die weitere Steuerung verfügbar sein, ohne dass der Benutzer das vollständige Ergebnis manuell kopieren muss.

Die Bridge soll nicht auf Dorfschaft beschränkt sein.

Dorfschaft dient zunächst als Referenzprojekt und erstes produktives Integrationsziel.

---

# 3. Nicht-Ziele der ersten Version

Die erste Version soll bewusst keine vollständige autonome Entwicklungsplattform darstellen.

Insbesondere zunächst nicht:

- selbstständige fachliche Projektentscheidungen
- automatische Freigabe kritischer Git-Aktionen
- automatisches Merge in main
- autonomes Deployment
- produktive Datenbankänderungen
- automatische Architekturentscheidungen
- automatische Sicherheitsfreigaben
- unkontrollierter Zugriff auf beliebige Repositories
- direkte Manipulation laufender ChatGPT-Konversationen ohne dafür vorgesehene Schnittstelle

Die Bridge transportiert und verwaltet Aufträge und Ergebnisse.

Die fachliche Steuerung bleibt beim Steuerprozess bzw. Benutzer.

---

# 4. Grundarchitektur

Die Zielarchitektur besteht aus fünf logischen Komponenten.

## 4.1 Steuerprozess

Der Steuerprozess erzeugt einen Auftrag.

Beispiele:

- ChatGPT-Steuerchat
- später eine Weboberfläche
- CLI
- API
- automatisierter Workflow

Der Steuerprozess definiert mindestens:

- Projekt
- Auftrags-ID
- Zielsystem
- Repository
- Worktree
- Modell
- Denk-/Reasoning-Stufe
- Arbeitsanweisung
- Schreibrechte
- Git-Rechte
- erlaubte Dateien
- verbotene Aktionen
- erwartete Tests
- erwartetes Ergebnisformat

---

## 4.2 Auftragsspeicher

Die Bridge speichert jeden Auftrag strukturiert.

Konzeptionell:

```text
bridge/
  projects/
  tasks/
  results/
  runs/
  state/
  logs/
```

Ein Auftrag besitzt eine unveränderliche Identität.

Beispiel:

```text
project: dorfschaft
task_id: DORF-008
bridge_task_id: BRIDGE-0042
```

Die Bridge-ID ist systemweit eindeutig.

Die projektspezifische ID bleibt zusätzlich erhalten.

---

# 5. Standardisiertes Auftragsschema

Jeder Auftrag soll mindestens folgende Felder besitzen:

```text
schema_version
bridge_task_id
project_id
project_task_id
created_at
created_by
target_machine
target_environment
repository
branch
worktree
expected_head
model
reasoning_level
task_class
multi_agent_allowed
instructions
allowed_write_scope
forbidden_actions
required_tests
git_policy
result_contract
status
```

Optionale Felder:

```text
dependencies
parent_task
previous_run
retry_policy
usage_limit_resume
timeout_policy
handover_reference
expected_files
migration_constraints
security_level
approval_required
```

---

# 6. Ergebnisformat

Codex-Ergebnisse dürfen nicht nur als unstrukturierter Chattext behandelt werden.

Jeder Lauf erhält ein standardisiertes Ergebnisobjekt.

Beispiel:

```text
bridge_task_id
project_task_id
run_id
started_at
finished_at
model_used
reasoning_used
machine
environment
repository
branch
head_before
head_after
status
files_changed
tests_run
tests_passed
tests_failed
tests_blocked
findings
git_actions
commit
push
remote_head
next_recommended_action
raw_result
```

Zusätzlich:

```text
interrupted
interruption_reason
resume_possible
worktree_dirty
index_clean
scope_check
diff_check
```

Damit kann ein Steuerprozess Ergebnisse maschinell auswerten.

---

# 7. Zustandsmodell

Ein Auftrag besitzt einen eindeutigen Status.

Vorgeschlagene Zustände:

```text
CREATED
READY
CLAIMED
RUNNING
INTERRUPTED
WAITING_FOR_RESUME
COMPLETED
FAILED
BLOCKED
REVIEW_REQUIRED
APPROVAL_REQUIRED
ARCHIVED
```

Wichtig:

`COMPLETED` bedeutet nur:

> Codex hat den Auftrag entsprechend seinem Ergebnisvertrag beendet.

Es bedeutet nicht automatisch:

> fachlich freigegeben oder zur Integration bereit.

Dafür können zusätzliche projektspezifische Zustände verwendet werden.

---

# 8. Umgang mit Usage-Limits und Unterbrechungen

Ein zentraler Anwendungsfall ist die Wiederaufnahme unterbrochener Codex-Aufträge.

Die Bridge muss unterscheiden zwischen:

- technischer Fehler
- Toolchain-Fehler
- Benutzerabbruch
- Usage-Limit
- Rechnerabschaltung
- Netzwerkunterbrechung
- Prozessabbruch

Bei einem Usage-Limit darf kein neuer fachlicher Auftrag erzeugt werden.

Der bestehende Auftrag bleibt bestehen:

```text
BRIDGE_TASK_ID: unverändert
PROJECT_TASK_ID: unverändert
STATUS: WAITING_FOR_RESUME
```

Nach Wiederaufnahme erhält lediglich der Lauf eine neue Run-ID.

Beispiel:

```text
DORF-008

Run 1:
DORF008-RUN-01

Unterbrechung:
USAGE_LIMIT

Run 2:
DORF008-RUN-02
```

Dadurch wird verhindert, dass bereits ausgeführte Arbeit unnötig wiederholt wird.

---

# 9. Erkennung eines abgeschlossenen Codex-Auftrags

Die Bridge soll mehrere Erkennungsmechanismen unterstützen.

## Stufe 1

Ergebnisdatei bzw. Ergebnisobjekt wird nach Codex-Abschluss gespeichert.

Der Auftrag erhält:

```text
status = COMPLETED
```

Der Steuerprozess kann diesen Status abrufen.

## Stufe 2

Ein lokaler Bridge-Agent überwacht den Auftrags-/Ergebnisbereich.

Sobald ein Ergebnis vorliegt, wird ein Ereignis erzeugt.

## Stufe 3

Webhook-/Event-basierter Rückkanal.

Zielwert:

> Fertigstellung eines Auftrags soll möglichst innerhalb von 1–2 Minuten erkennbar sein.

Später kann die Erkennungszeit weiter reduziert werden.

---

# 10. Kommunikationsprinzip

Die Bridge darf nicht davon abhängen, dass zwei Chats direkt miteinander kommunizieren können.

Stattdessen wird ein neutraler Übergabekanal verwendet:

```text
Steuerchat
    ↓
strukturierter Auftrag
    ↓
Bridge
    ↓
Codex
    ↓
strukturiertes Ergebnis
    ↓
Bridge
    ↓
Steuerprozess
```

Damit bleibt das System unabhängig von einem bestimmten Chat-Frontend.

---

# 11. Projektunabhängigkeit

Die Bridge selbst enthält keine Dorfschaft-Fachlogik.

Projektbezogene Regeln werden über Projektprofile geladen.

Beispiel:

```text
projects/dorfschaft/project.yaml
projects/bess-msrechner/project.yaml
```

Ein Projektprofil könnte enthalten:

```text
project_id
repository
default_branch
worktree_root
allowed_machines
default_model_policy
git_policy
migration_policy
test_policy
handover_policy
task_number_prefix
```

Für Dorfschaft:

```text
project_id: dorfschaft
task_prefix: DORF
```

Für die Bridge selbst:

```text
project_id: codex-control-bridge
task_prefix: BRIDGE
```

Damit werden Auftragsnummern nicht vermischt.

---

# 12. Maschinenmodell

Die Bridge muss mehrere Rechner und Ausführungsumgebungen unterscheiden können.

Beispiel:

```text
physical_machine
logical_environment
os
runtime
worktree
capabilities
```

Dadurch kann ein Auftrag beispielsweise gezielt verlangen:

```text
physical_machine: DES11
environment: DES01
runtime: WSL
```

oder:

```text
physical_machine: DES11
environment: WINDOWS_NATIVE
runtime: PowerShell 7
```

Die Bridge darf Maschinenidentität nicht nur aus einem einzelnen Hostnamen ableiten.

---

# 13. Sicherheitsmodell

Die Bridge darf niemals allein aufgrund eines eingegangenen Auftrags unbeschränkte Rechte erhalten.

Jeder Auftrag besitzt ein Berechtigungsprofil.

Beispiel:

```text
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

Standard:

```text
READ_ONLY
```

Erweiterte Rechte müssen explizit im Auftrag vorhanden sein.

Besonders kritische Aktionen:

```text
MERGE
DEPLOY
DATABASE_WRITE
FORCE_PUSH
MIGRATION_PRODUCTION
```

dürfen nicht implizit freigegeben werden.

---

# 14. Git-Sicherheit

Die Bridge muss Git-Zustände als Teil der Auftragsidentität behandeln.

Vor einem Lauf mindestens:

```text
repository
branch
HEAD
upstream
ahead/behind
worktree status
index status
```

Bei relevanten Aufträgen zusätzlich:

```text
expected_head
allowed_changed_files
expected_diff_hash
```

Ein Auftrag darf abbrechen, wenn die erwartete Ausgangslage nicht stimmt.

Dadurch wird verhindert, dass Codex versehentlich im falschen Worktree oder auf einem veralteten Branch arbeitet.

---

# 15. Ergebnisintegrität

Ergebnisse sollen kryptografisch bzw. technisch eindeutig einem Auftrag zugeordnet werden können.

Mindestens speichern:

```text
bridge_task_id
project_task_id
run_id
repository
branch
head
timestamp
```

Optional:

```text
task_hash
result_hash
diff_hash
```

Dadurch können Handover und spätere Audits feststellen:

> Dieses Ergebnis gehört exakt zu diesem Auftrag und diesem Repositoryzustand.

---

# 16. Audit

Alle wichtigen Zustandsänderungen sollen nachvollziehbar sein.

Beispiele:

```text
TASK_CREATED
TASK_CLAIMED
TASK_STARTED
TASK_INTERRUPTED
TASK_RESUMED
TASK_COMPLETED
RESULT_WRITTEN
COMMIT_CREATED
PUSH_COMPLETED
REVIEW_REQUESTED
```

Auditinformationen:

```text
timestamp
actor
machine
task
run
old_state
new_state
reason
```

---

# 17. Speicherung

Für die erste Version wird eine einfache, transparente Speicherung bevorzugt.

Mögliche Stufe 1:

```text
JSON/YAML + Git
```

Spätere Version:

```text
SQLite
```

oder

```text
PostgreSQL
```

Die erste Implementierung soll nicht unnötig mit einer komplexen Serverarchitektur beginnen.

---

# 18. Repositorystruktur des neuen Projekts

Vorgeschlagen:

```text
codex-control-bridge/
│
├── README.md
├── docs/
│   ├── architecture/
│   ├── concepts/
│   ├── protocols/
│   ├── security/
│   └── handover/
│
├── schemas/
│   ├── task.schema.json
│   ├── result.schema.json
│   └── project.schema.json
│
├── projects/
│   └── examples/
│
├── src/
│   ├── bridge/
│   ├── runner/
│   ├── watcher/
│   ├── storage/
│   └── adapters/
│
├── tests/
│
├── scripts/
│
└── work-packages/
```

---

# 19. Entwicklung in Stufen

## STUFE 0 – Architektur und Protokoll

Ziel:

Das Austauschformat vollständig definieren.

Erstellen:

- Task Schema
- Result Schema
- Zustandsmodell
- Projektprofil
- Rechteprofil
- Auditformat
- Fehler-/Resume-Modell

Keine Codex-Automatisierung erforderlich.

---

## STUFE 1 – Datei-/Repository-basierte Bridge

Ziel:

Manuelles Copy/Paste der umfangreichen Codex-Ergebnisse weitgehend beseitigen.

Ablauf:

```text
Steuerprozess
→ erzeugt Auftrag
→ Task-Datei

Codex
→ liest Auftrag
→ arbeitet
→ schreibt Result-Datei

Bridge
→ erkennt Result-Datei
→ aktualisiert Status
```

Beispiel:

```text
tasks/BRIDGE-0042/task.json

results/BRIDGE-0042/result.json
```

Diese Stufe soll bereits produktiv nutzbar sein.

Geschätzter Implementierungsaufwand:

ca. 1–2 Arbeitstage für eine einfache robuste Version.

---

# 20. STUFE 2 – Watcher und automatischer Runner

Ein lokaler Agent läuft auf der Arbeitsmaschine.

Funktionen:

- neue Aufgaben erkennen
- richtige Maschine prüfen
- richtigen Worktree öffnen
- Auftrag claimen
- Codex starten
- Lauf überwachen
- Ergebnis erfassen
- Status aktualisieren
- Usage-Limit erkennen
- Wiederaufnahme vorbereiten

Der Benutzer muss nicht mehr jeden Auftrag manuell in Codex einfügen.

---

# 21. STUFE 3 – Ereignisbasierte Steuerung

Ziel:

Nahezu automatische Steuerkette.

```text
Steuerchat
→ Auftrag
→ Bridge
→ Codex
→ Ergebnis
→ Bridge Event
→ Steuerprozess
→ Bewertung
→ Folgeauftrag
```

Der Mensch bleibt bei definierten Freigabepunkten beteiligt.

---

# 22. Integrationsziel Dorfschaft

Dorfschaft wird später als erstes Referenzprojekt angebunden.

Die Integration darf das aktuelle Dorfschaft-Projekt zunächst nicht verändern.

Zunächst wird nur ein Projektadapter erstellt.

Beispiel:

```text
projects/dorfschaft/project.yaml
```

Dieser kennt unter anderem:

- Repository
- Worktree-Konvention
- DORF-Auftragsnummern
- Maschinen HAM01/DES01
- Git-Gates
- Testregeln
- Modellregeln
- Handover-Regeln

Die bestehende Dorfschaft-Steuerlogik bleibt maßgeblich.

Die Bridge automatisiert nur die Übertragung und Zustandserfassung.

---

# 23. Erste Dorfschaft-Integration

Der erste reale Integrationstest soll absichtlich ungefährlich sein.

Beispiel:

```text
DORF-BRIDGE-TEST-001
```

Aufgabe:

Read-only Repositorystatus erfassen.

Erwartetes Ergebnis:

```text
machine
environment
repository
branch
head
ahead/behind
worktree status
```

Keine Sourceänderung.

Keine Git-Schreibaktion.

Erst nach erfolgreichem Read-only-Test dürfen komplexere Dorfschaft-Aufträge verwendet werden.

---

# 24. Trennung der Projekte

Das Bridge-Projekt erhält:

```text
BRIDGE-001
BRIDGE-002
BRIDGE-003
```

Dorfschaft behält:

```text
DORF-001
DORF-002
DORF-003
```

Die Bridge darf Dorfschaft-Auftragsnummern speichern, aber nicht selbst deren Nummerierungslogik übernehmen.

Beispiel:

```text
bridge_task_id: BRIDGE-0042
external_task_id: DORF-008
project: dorfschaft
```

---

# 25. Handover

Das Bridge-Projekt muss selbst vollständig rechnerunabhängig übergabefähig sein.

Ein Wechsel zwischen Rechnern darf keine lokale versteckte Abhängigkeit erzeugen.

Versionierbare Zustände gehören ins Repository.

Nicht akzeptabel als alleinige SSOT:

- Chatverlauf
- lokale temporäre Datei
- Clipboard
- ChatGPT Memory
- Codex-Konversationshistorie
- nur auf einem Rechner vorhandener Zustand

Leitregel:

> Auftrag, Zustand und Ergebnis müssen außerhalb des Chatverlaufs reproduzierbar auffindbar sein.

---

# 26. Fehlerprinzip

Bei Unsicherheit gilt:

**fail-closed**

Beispiele:

- falscher Worktree
- unerwarteter HEAD
- unbekannter Auftrag
- Resultat für falsche Task-ID
- unerlaubte Git-Aktion
- nicht eindeutige Maschinenidentität
- beschädigte Task-Datei
- Schemafehler

Dann:

```text
BLOCKED
```

statt eigenständig zu improvisieren.

---

# 27. Modellsteuerung

Die Bridge soll Modell und Denkstufe als Auftragsparameter transportieren.

Beispiel:

```text
model: GPT-5.6 Luna
reasoning: Medium
```

Sie entscheidet zunächst nicht selbstständig über Modelle.

Später kann eine Modellpolicy ergänzt werden.

Grundprinzip:

> Das schwächste zuverlässig geeignete Modell mit der niedrigsten ausreichenden Denkstufe verwenden.

Qualität, Sicherheit, Datenintegrität und korrekte Git-/Teststeuerung haben Vorrang vor Tokenersparnis.

---

# 28. Multi-Agenten

Aufträge können deklarieren:

```text
multi_agent_allowed: true
max_agents: 3
```

Die Bridge selbst muss dabei keine fachliche Agentenaufteilung vornehmen.

Der ausführende Codex-Agent entscheidet entsprechend der Auftragsanweisung.

Ergebnisse der Unteragenten müssen dem Hauptlauf zugeordnet bleiben.

---

# 29. Akzeptanzkriterien Stufe 1

Stufe 1 gilt als erfolgreich, wenn:

1. Ein standardisierter Auftrag erzeugt werden kann.
2. Jeder Auftrag eine eindeutige Bridge-ID besitzt.
3. Projekt-ID und externe Auftrags-ID separat gespeichert werden.
4. Codex einen Auftrag lesen kann.
5. Codex ein standardisiertes Ergebnis erzeugen kann.
6. Auftrag und Ergebnis eindeutig zusammengehören.
7. Unterbrechungen gespeichert werden können.
8. Ein Auftrag nach Unterbrechung fortgesetzt werden kann.
9. Ergebnisse nach Rechnerwechsel weiterhin verfügbar sind.
10. Ein Steuerprozess erkennen kann, dass ein Auftrag abgeschlossen wurde.
11. Keine direkte Chat-zu-Chat-Verbindung vorausgesetzt wird.
12. Dorfschaft nicht verändert werden muss, um Stufe 1 zu entwickeln.

---

# 30. Akzeptanzkriterien Dorfschaft-Integration

Eine spätere Dorfschaft-Integration gilt erst als freigegeben, wenn:

- Bridge separat getestet
- Task-/Result-Schema stabil
- falsche Projekt-/Worktree-Zuordnung fail-closed
- Read-only-Dorfschaft-Test PASS
- DORF-Auftragsnummer bleibt erhalten
- Maschinenidentität korrekt
- Git-Gates funktionieren
- kein automatischer Merge
- kein automatisches Deployment
- kein produktiver DB-Zugriff
- vollständige Auditspur vorhanden

---

# 31. Erstes Entwicklungsprogramm

Empfohlene Reihenfolge:

### BRIDGE-001
Repository und Grundstruktur aufbauen.

### BRIDGE-002
Task-Schema definieren.

### BRIDGE-003
Result-Schema definieren.

### BRIDGE-004
Zustands-/Resume-Modell implementieren.

### BRIDGE-005
Lokale Dateiablage und Validierung implementieren.

### BRIDGE-006
CLI für Auftragserstellung und Statusanzeige.

### BRIDGE-007
Codex-Result-Importer.

### BRIDGE-008
Watcher für abgeschlossene Resultate.

### BRIDGE-009
Unterbrechung/Usage-Limit/Wiederaufnahme testen.

### BRIDGE-010
Projektprofil-Mechanismus.

### BRIDGE-011
Dorfschaft-Adapter nur konzeptionell und read-only.

### BRIDGE-012
Erster Dorfschaft-Read-only-Integrationstest.

---

# 32. Technische Leitregel

Die Bridge soll möglichst wenige projektspezifische Annahmen enthalten.

Der Core verarbeitet:

```text
Task
Run
Result
Project
Machine
State
Permission
Event
```

Dorfschaft-spezifische Regeln gehören in einen Adapter beziehungsweise ein Projektprofil.

---

# 33. Langfristiges Zielbild

Das spätere System soll einen Ablauf wie diesen ermöglichen:

```text
ChatGPT-Steuerung
        │
        ▼
BRIDGE-Task erzeugen
        │
        ▼
Codex Control Bridge
        │
        ▼
Codex-Agent
        │
        ▼
Tests / Repository / Worktree
        │
        ▼
strukturiertes Resultat
        │
        ▼
Codex Control Bridge
        │
        ▼
Steuerprozess erkennt Abschluss
        │
        ▼
Review / Folgeauftrag / Freigabe
```

Dabei bleiben:

- Projekt-SSOT
- Git-SSOT
- Sicherheitsregeln
- Freigabegates
- menschliche Kontrolle

erhalten.

---

# 34. Startanweisung für einen neuen Chat

Setze ein neues, von Dorfschaft unabhängiges Projekt mit dem Namen

**Codex Control Bridge**

auf Grundlage dieses Konzeptes auf.

Das Projekt soll eine projektunabhängige Vermittlungsschicht für strukturierte Aufträge und Ergebnisse zwischen einem Steuerprozess und Codex entwickeln.

Dorfschaft ist ausschließlich das erste spätere Referenz- und Integrationsprojekt und darf während der Entwicklung der Bridge nicht verändert oder blockiert werden.

Verwende für dieses Projekt ausschließlich fortlaufende Auftragsnummern:

**BRIDGE-001, BRIDGE-002, BRIDGE-003, …**

Beginne mit Architektur und Stufe 1.

Priorität haben:

1. eindeutiges Task-Schema
2. eindeutiges Result-Schema
3. Zustandsmodell
4. Unterbrechungs-/Resume-Modell
5. projektunabhängige Speicherung
6. sichere Maschinen-/Repository-/Worktree-Identität
7. Git- und Berechtigungsgrenzen
8. lokale Erkennung abgeschlossener Aufträge
9. vollständige Handover-Fähigkeit
10. späterer read-only Dorfschaft-Adapter

Keine Dorfschaft-Dateien verändern.

Keine produktiven Integrationen durchführen, bevor Stufe 1 isoliert getestet und freigegeben wurde.

Das schwächste zuverlässig geeignete Modell mit der niedrigsten ausreichenden Denkstufe verwenden. Modell und Denkstufe vor jedem Codex-Arbeitsblock ausdrücklich nennen.

Vor größeren Implementierungsblöcken Multi-Agenten-Eignung prüfen.

Git-Schreibaktionen nur nach ausdrücklich freigegebenem Scope.

Beginne mit:

**BRIDGE-001 – Bestandsfreie Projektinitialisierung und verbindliche Architekturgrundlage.**