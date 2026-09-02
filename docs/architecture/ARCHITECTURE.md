# Architekturgrundlage — Codex Control Bridge

> **Status:** verbindlich ab BRIDGE-001.
> Diese Datei ist die maßgebliche Architekturgrundlage. Spätere Arbeitspakete
> konkretisieren sie, dürfen ihr aber nicht widersprechen. Abweichungen erfordern
> ein ausdrückliches Änderungs-Arbeitspaket, das diese Datei fortschreibt.

---

## 1. Zweck

Die Codex Control Bridge (CCB) vermittelt strukturierte **Aufträge** und
**Ergebnisse** zwischen einem **Steuerprozess** und **Codex**:

```
Steuerprozess → Auftrag → Bridge → Codex → Ergebnis → Bridge → Steuerprozess
```

Ziel ist es, die heute manuellen Übergaben (Copy/Paste) zu standardisieren und
schrittweise zu automatisieren, ohne fachliche Steuerung oder
Sicherheitsentscheidungen an die Bridge abzugeben.

---

## 2. Logische Komponenten

Die Zielarchitektur besteht aus fünf logischen Komponenten:

| Komponente | Verantwortung |
|------------|---------------|
| **Steuerprozess** | Erzeugt Aufträge, bewertet Ergebnisse, erzeugt Folgeaufträge. Nicht Teil des Bridge-Core. |
| **Auftragsspeicher** | Persistiert Aufträge, Läufe, Ergebnisse, Zustände und Auditspur strukturiert und versionierbar. |
| **Runner** | Führt einen Auftrag in der richtigen Maschine/Umgebung/Worktree aus (Stufe 2+); in Stufe 1 durch den Benutzer + Codex. |
| **Watcher** | Erkennt abgeschlossene Ergebnisse und erzeugt Ereignisse (Stufe 2+). |
| **Adapter / Projektprofil** | Liefert projektspezifische Regeln (Repository, Worktree-Konventionen, Git-Gates, Modell-/Testregeln). |

Der **Core** verarbeitet ausschließlich generische Konzepte:

```
Task · Run · Result · Project · Machine · State · Permission · Event
```

Projektspezifische Regeln gehören **nicht** in den Core, sondern in einen
Adapter bzw. ein Projektprofil (`projects/<projekt>/project.yaml`).

---

## 3. Kommunikationsprinzip: neutraler Übergabekanal

Die Bridge setzt **keine** direkte Chat-zu-Chat-Verbindung voraus. Stattdessen
läuft die Übergabe über einen neutralen, versionierbaren Kanal:

```
Steuerchat
   ↓  (strukturierter Auftrag)
Bridge   ── task ──►  Codex
Bridge   ◄─ result ──  Codex
   ↓  (strukturiertes Ergebnis)
Steuerprozess
```

Das System bleibt dadurch unabhängig von einem bestimmten Chat-Frontend.

---

## 4. Identität eines Auftrags

Ein Auftrag besitzt eine **unveränderliche Identität**:

```
bridge_task_id      # systemweit eindeutig, vergibt die Bridge  (z. B. BRIDGE-0042)
project_id          # z. B. dorfschaft
project_task_id     # externe ID des Projekts (z. B. DORF-008)
```

- Die `bridge_task_id` ist die primäre, systemweite Identität.
- Die projektspezifische ID bleibt zusätzlich erhalten.
- Nummernräume werden **nie vermischt**. Die Bridge speichert externe IDs, aber
  übernimmt nicht deren Nummerierungslogik.

Ein Auftrag kann mehrere **Läufe** (`run_id`) haben — siehe Resume-Modell.

---

## 5. Zustandsmodell

Jeder Auftrag hat genau einen Status:

```
CREATED → READY → CLAIMED → RUNNING → COMPLETED
                     │           │
                     │           ├─► INTERRUPTED → WAITING_FOR_RESUME → (RUNNING)
                     │           ├─► FAILED
                     │           └─► BLOCKED
                     │
                     └─► BLOCKED

Weitere: REVIEW_REQUIRED · APPROVAL_REQUIRED · ARCHIVED
```

**Wichtige Semantik:**
`COMPLETED` bedeutet nur: *Codex hat den Auftrag entsprechend seinem
Ergebnisvertrag beendet.* Es bedeutet **nicht** fachlich freigegeben oder
integrationsbereit. Dafür dienen projektspezifische Zustände bzw.
`REVIEW_REQUIRED` / `APPROVAL_REQUIRED`.

Das vollständige Zustands- und Übergangsmodell wird in **BRIDGE-004**
implementiert.

---

## 6. Lauf- und Resume-Modell (Unterbrechungen)

Die Bridge unterscheidet Unterbrechungsursachen:

```
technischer Fehler · Toolchain-Fehler · Benutzerabbruch · Usage-Limit
· Rechnerabschaltung · Netzwerkunterbrechung · Prozessabbruch
```

Bei einem **Usage-Limit** wird **kein** neuer fachlicher Auftrag erzeugt. Der
bestehende Auftrag bleibt bestehen:

```
bridge_task_id : unverändert
project_task_id: unverändert
status         : WAITING_FOR_RESUME
```

Nach Wiederaufnahme erhält nur der **Lauf** eine neue `run_id`:

```
DORF-008
  Run 1: DORF008-RUN-01   → INTERRUPTED (USAGE_LIMIT)
  Run 2: DORF008-RUN-02   → (Fortsetzung)
```

So wird verhindert, dass bereits erledigte Arbeit unnötig wiederholt wird.
Detaillierte Umsetzung in **BRIDGE-004** und **BRIDGE-009**.

---

## 7. Sicherheitsmodell (verbindlich)

Details in [`../security/SECURITY-MODEL.md`](../security/SECURITY-MODEL.md).

- **Default = `READ_ONLY`.** Ein eingegangener Auftrag verschafft der Bridge
  niemals von selbst erweiterte Rechte.
- Erweiterte Rechte müssen **explizit** im Auftrag stehen.
- Kritische Aktionen — `MERGE`, `DEPLOY`, `DATABASE_WRITE`, `FORCE_PUSH`,
  `MIGRATION_PRODUCTION` — dürfen **nie implizit** freigegeben werden.
- **Fail-closed:** Bei falschem Worktree, unerwartetem HEAD, unbekanntem
  Auftrag, Ergebnis für falsche Task-ID, unerlaubter Git-Aktion, nicht
  eindeutiger Maschinenidentität, beschädigter Task-Datei oder Schemafehler →
  `BLOCKED`, statt zu improvisieren.

---

## 8. Git-Sicherheit

Der Git-Zustand ist **Teil der Auftragsidentität**. Vor einem Lauf wird
mindestens erfasst:

```
repository · branch · HEAD · upstream · ahead/behind · worktree status · index status
```

Bei relevanten Aufträgen zusätzlich `expected_head`, `allowed_changed_files`,
`expected_diff_hash`. Stimmt die erwartete Ausgangslage nicht, **darf der
Auftrag abbrechen** (fail-closed), damit Codex nicht im falschen Worktree oder
auf einem veralteten Branch arbeitet.

---

## 9. Maschinenmodell

Die Bridge unterscheidet mehrere Rechner und Ausführungsumgebungen und leitet
Maschinenidentität **nicht allein aus einem Hostnamen** ab:

```
physical_machine · logical_environment · os · runtime · worktree · capabilities
```

Beispiel:

```
physical_machine: DES11
environment:      DES01
runtime:          WSL
```

---

## 10. Ergebnisintegrität & Audit

Jedes Ergebnis wird eindeutig einem Auftrag und Repositoryzustand zugeordnet
(mindestens `bridge_task_id`, `project_task_id`, `run_id`, `repository`,
`branch`, `head`, `timestamp`; optional `task_hash`, `result_hash`,
`diff_hash`).

Alle wichtigen Zustandsänderungen sind nachvollziehbar (`TASK_CREATED`,
`TASK_CLAIMED`, `TASK_STARTED`, `TASK_INTERRUPTED`, `TASK_RESUMED`,
`TASK_COMPLETED`, `RESULT_WRITTEN`, `COMMIT_CREATED`, `PUSH_COMPLETED`,
`REVIEW_REQUESTED`) mit `timestamp · actor · machine · task · run · old_state ·
new_state · reason`. Audit-Format: **BRIDGE-004/005**.

---

## 11. Speicherung

- **Stufe 1:** einfache, transparente Ablage — `JSON`/`YAML` + Git.
- **Später:** `SQLite`, danach optional `PostgreSQL`.

Die erste Implementierung beginnt bewusst **nicht** mit komplexer
Serverarchitektur. Versionierbare Zustände gehören ins Repository.

Konzeptioneller Ablagepfad (Stufe 1):

```
tasks/BRIDGE-0042/task.json
results/BRIDGE-0042/result.json
```

---

## 12. Projektunabhängigkeit

Der Core enthält keine Fachlogik. Projektbezogene Regeln kommen über
Projektprofile:

```
projects/dorfschaft/project.yaml       (task_prefix: DORF)
projects/codex-control-bridge/...      (task_prefix: BRIDGE)
```

Ein Projektprofil kennt u. a. `project_id`, `repository`, `default_branch`,
`worktree_root`, `allowed_machines`, `default_model_policy`, `git_policy`,
`migration_policy`, `test_policy`, `handover_policy`, `task_number_prefix`.
Mechanismus: **BRIDGE-010**.

---

## 13. Modellsteuerung

Modell und Denkstufe werden als **Auftragsparameter** transportiert
(`model`, `reasoning_level`). Die Bridge entscheidet zunächst nicht
selbstständig über Modelle. Leitregel:

> Das schwächste zuverlässig geeignete Modell mit der niedrigsten ausreichenden
> Denkstufe verwenden. Qualität, Sicherheit, Datenintegrität und korrekte
> Git-/Teststeuerung haben Vorrang vor Tokenersparnis.

Modell und Denkstufe werden vor jedem Codex-Arbeitsblock ausdrücklich genannt.

---

## 14. Entwicklungsstufen

| Stufe | Inhalt |
|-------|--------|
| **0** | Architektur & Protokoll: Task-/Result-/Project-Schema, Zustands-, Resume-, Rechte-, Auditmodell. Keine Automatisierung nötig. |
| **1** | Datei-/Repository-basierte Bridge. Beseitigt manuelles Copy/Paste umfangreicher Ergebnisse. Bereits produktiv nutzbar. |
| **2** | Lokaler Watcher + automatischer Runner. |
| **3** | Ereignisbasierte Steuerkette (Webhook/Event-Rückkanal). |

Bei allen Stufen bleiben Projekt-SSOT, Git-SSOT, Sicherheitsregeln,
Freigabegates und menschliche Kontrolle erhalten.

---

## 15. Bindende Leitregeln (Zusammenfassung)

1. Projektunabhängiger Core; Fachlogik nur in Adaptern/Profilen.
2. SSOT im Repository — nie Chat, Clipboard, Memory oder Einzelrechner allein.
3. Fail-closed bei jeder Unsicherheit → `BLOCKED`.
4. Least privilege; kritische Aktionen nie implizit.
5. Git-Zustand ist Teil der Auftragsidentität.
6. Getrennte Nummernräume (`BRIDGE-*` vs. externe IDs).
7. Dorfschaft während der Bridge-Entwicklung nicht verändern; erste Integration
   read-only.
8. Keine produktive Integration vor isoliert getesteter und freigegebener
   Stufe 1.
