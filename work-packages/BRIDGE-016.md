# BRIDGE-016 — Copy-Paste-Board (Terminal) + Befehlsreferenz

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-016 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-010, BRIDGE-014, BRIDGE-015 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Kontext

Das eigentliche Ziel des Projekts (s. CCB-UEBERGABE.md Abschnitt 6): ein
Terminal-Befehl, der projektübergreifend zeigt, welcher Auftrag als Nächstes
kopiert werden muss und in welcher Reihenfolge — plus, neu entschieden, eine
Befehlsreferenz für die gängigsten Kommandos im selben Terminal (Bridge
starten, Übergabe vorbereiten, u. a.), damit der Nutzer sie nicht jedes Mal
neu suchen muss.

**Wichtige Architektur-Klarstellung, damit nichts überbaut wird:** Aufträge
(egal ob `BRIDGE-xxx` oder `DORF-xxx`) liegen alle in **einem einzigen,
zentralen Store** — diesem Repo (`tasks/`, `results/`, `audit/`). Es gibt
**keine** separaten Task-Stores in den anderen Projekt-Repos (Dorfschaft
etc.) — "projektübergreifend" heißt hier: verschiedene `project_id`-Werte
innerhalb desselben Stores, unterschieden über `task_prefix`. Die neue
Maschinen-Registry wird **nicht** gebraucht, um Aufträge zu finden — nur um
für die Befehlsreferenz reale lokale Pfade anderer Projekt-Repos aufzulösen
(`E:\_DEV\<repository>`). Bitte keine Multi-Repo-Traversierung bauen, das ist
nicht nötig.

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/registry.schema.yaml` — neues Schema, COMPUTERNAME → lokale Basis.
- `registry.yaml` (Repo-Wurzel) — Daten: `HAM11`/`DES11` → `E:\_DEV`.
  Gegen das Schema validiert (siehe Kommentar in der Datei für den Zweck:
  ausschließlich Befehlsreferenz, nicht Auftragssuche).

## Von Claude Code umzusetzen

### 1) `src/bridge/registry.py` (neues Modul)

```python
def load_registry(root, schema_dir) -> dict: ...
    # lädt + validiert registry.yaml gegen registry.schema.yaml (fail-closed,
    # gleiches Muster wie profiles.load_profile)

def machine_name(explicit=None) -> str:
    # explicit (z. B. --machine-Flag) hat Vorrang, sonst os.environ["COMPUTERNAME"],
    # sonst platform.node() als Fallback (für Nicht-Windows/Tests)

def resolve_base(root, schema_dir, *, explicit_machine=None, env_override_name="CCB_PROJECT_BASE") -> str:
    # 1) wenn env_override_name gesetzt ist (os.environ) -> dessen Wert, fertig
    # 2) sonst: registry.yaml laden, machine_name() nachschlagen
    # 3) unbekannte Maschine -> RegistryError (fail-closed), klare Meldung
    #    mit dem tatsächlichen Maschinennamen und Hinweis auf CCB_PROJECT_BASE

def project_local_path(root, schema_dir, project_id, *, explicit_machine=None) -> str | None:
    # base = resolve_base(...); Profil laden (profiles.load_profile) für
    # `repository`; Pfad = os.path.join(base, repository).
    # Fail-SOFT hier (anders als resolve_base!): wenn Profil fehlt ODER
    # resolve_base fehlschlägt ODER der Pfad auf DIESER Maschine nicht
    # existiert -> None zurückgeben, NICHT werfen. Aufrufer entscheidet, wie
    # das angezeigt wird. (Grund: das Board soll nie wegen einem einzelnen
    # nicht auflösbaren Projekt komplett abbrechen - "Fehlende/leere Projekte:
    # fail-soft anzeigen, kein Abbruch", s. CCB-UEBERGABE.md Abschnitt 6.)
```

Neue Exception `RegistryError(StoreError)` in registry.py oder store.py,
konsistent mit den bestehenden Fehlerklassen.

### 2) Audit-Zeitstempel-Hilfsfunktion für "wartet seit"

In `src/bridge/store.py`, neue Methode auf `Store`:

```python
def last_transition_at(self, task_id, new_state) -> str | None:
    """Letzter Zeitpunkt (ISO-Timestamp), zu dem task_id in new_state
    gewechselt ist. Liest audit.jsonl einmal komplett (Datei ist klein),
    gibt den timestamp des letzten passenden Eintrags zurück, sonst None."""
```

Nutzt `self.audit_file`, liest zeilenweise JSON, filtert auf
`bridge_task_id == task_id and new_state == new_state`, nimmt den letzten
Treffer (Datei ist append-only, also chronologisch).

### 3) CLI-Befehl `ccb board` (rein lesend, keine Schreibzugriffe)

Neuer Unterbefehl (kein Sub-Sub-Befehl nötig, top-level wie `resume`):

```
bridge board [--machine NAME]
```

Ablauf:
1. Alle Aufträge laden (bestehendes Muster wie `_list_tasks`, aber volle
   Task-Dokumente statt nur `(id, status)` — kleine Erweiterung oder neue
   Hilfsfunktion `_list_task_docs(store)`, die dieselbe Logik nutzt).
2. Filtern auf `status in {"WAITING_FOR_HANDOFF_TO_EXECUTOR", "WAITING_FOR_COPY_TO_CONTROL"}`.
3. Für jeden Treffer:
   - **Projekt-Spalte:** `task_prefix` aus dem Profil (`profiles.load_profile`,
     `project_id` aus dem Task). Fehlt das Profil → Fail-soft: `project_id`
     roh anzeigen statt abzubrechen.
   - **Richtung:** `WAITING_FOR_HANDOFF_TO_EXECUTOR` → `"Steuerchat -> Executor"`,
     `WAITING_FOR_COPY_TO_CONTROL` → `"Executor -> Steuerchat"`.
   - **Wartet seit:** `store.last_transition_at(task_id, status)` gegen
     `now()` (UTC), kurzformatig runden (`"12m"`, `"2h 14m"`, `"1d 3h"`).
     Kein Treffer im Audit (sollte nicht vorkommen, aber fail-soft) → `"?"`.
   - **Hinweis:** für jede ID in `depends_on`: falls diese Abhängigkeit im
     Store existiert und ihr `status` **nicht** `ARCHIVED` ist, Notiz
     `"(depends_on <id>, Status: <status>)"` anhängen. Fehlt die Abhängigkeit
     im Store ganz → keine Notiz (kann außerhalb dieses Stores liegen,
     Fail-soft, kein Fehler).
4. **Sortierung:** aufsteigend nach `bridge_task_id` (Text-Sortierung reicht
   dank fester 4-stelliger Nummer je Präfix).
5. **Ausgabe** als einfache, ausgerichtete Text-Tabelle:

```
#  Projekt      Auftrag      Richtung                    Wartet seit
1  DORF         DORF-0015    Executor -> Steuerchat       2h 14m
2  BRIDGE       BRIDGE-0016  Steuerchat -> Executor        12m
3  DORF         DORF-0016    Executor -> Steuerchat  (depends_on DORF-0015, Status: WAITING_FOR_COPY_TO_CONTROL)
```

Keine Treffer → `"(keine Aufträge warten auf Kopie)"`, Exit-Code 0 (kein
Fehlerzustand).

### 4) CLI-Befehl `ccb commands` (rein lesend, Befehlsreferenz)

```
bridge commands [--machine NAME] [--project PROJECT_ID]
```

Gibt eine kurze, kopierfertige Übersicht der gängigsten Befehle aus — **gibt
nichts aus, führt nichts aus** (Least-Privilege, reine Anzeige, wie das
Board). Diese Sektion **fail-closed**, falls `resolve_base` fehlschlägt
(unbekannte Maschine ohne `CCB_PROJECT_BASE`) — hier ist ein falscher/
geratener Pfad schlimmer als eine klare Fehlermeldung, im Unterschied zu
`project_local_path` in Punkt 3, das fail-soft ist.

Mindestinhalt (statisch formuliert, mit aufgelöstem Pfad für
`--project`, Default `codex-control-bridge`):

```
Board neu anzeigen:
  bridge board

Bridge-Watcher starten (wiederholt prüfen, bis Ctrl+C; --apply nur nach
Bestätigung, s. Guardrails):
  bridge watch loop --actor <dein-name>

Übergabe an die andere Maschine vorbereiten (PowerShell):
  cd <aufgelöster lokaler Pfad>
  .\scripts\handover-check.ps1

Übergabe vorbereiten (Bash/WSL, falls zutreffend):
  cd <aufgelöster lokaler Pfad>
  ./scripts/handover-check.sh

Tests dieses Projekts laufen lassen:
  <aus project.yaml test_policy.command, falls gesetzt, sonst Hinweis
   "kein Testbefehl im Profil hinterlegt">
```

### 5) Tests

- `tests/test_registry.py` (neu): `load_registry` lädt/validiert korrekt;
  `resolve_base` mit `CCB_PROJECT_BASE`-Override; `resolve_base` mit
  bekannter Maschine (per `explicit_machine`); `resolve_base` mit unbekannter
  Maschine → `RegistryError` (fail-closed); `project_local_path` fail-soft
  bei fehlendem Profil und bei unbekannter Maschine (gibt `None`, wirft
  nicht).
- `tests/test_store.py` ergänzen: `last_transition_at` findet den richtigen
  Zeitstempel, gibt `None` bei keinem Treffer.
- `tests/test_cli.py` ergänzen:
  - `board` zeigt Aufträge in beiden Wartezuständen, ignoriert andere Status,
    zeigt `depends_on`-Hinweis korrekt, zeigt `"(keine Aufträge...)"` bei
    leerem Store.
  - `board` bricht NICHT ab, wenn ein Task-`project_id` kein Profil hat
    (Fail-soft-Nachweis).
  - `commands` zeigt die erwarteten Abschnitte; schlägt mit klarer Meldung
    fehl, wenn Maschine unbekannt und kein `CCB_PROJECT_BASE` gesetzt ist.

### 6) Abschluss

- `python -m unittest discover -s tests` grün (121 bisherige + neue).
- `work-packages/BRIDGE-016.md`: Akzeptanzkriterien `[ ]` → `[x]` abhaken.
- Pflicht-Footer: `Auftrag: BRIDGE-016 / Lauf: RUN-01 / Status: ...`

## Scope

**Enthalten:** `registry.py`, `last_transition_at`, `ccb board`,
`ccb commands`, Tests.

**NICHT enthalten:**
- Ausführen von Befehlen aus dem Terminal heraus (nur Anzeige/Copy-Paste) —
  echte Aktionsausführung mit Bestätigung bleibt eigenes späteres Paket
  (ehemals BRIDGE-016 im Ursprungsplan, jetzt entsprechend weiter verschoben).
- Cross-Check Task-Präfix ↔ registriertes Projektprofil (bewusst
  zurückgestellt, s. BRIDGE-015-Notiz).
- Browser-Oberfläche (später, dünne Schicht über derselben Logik).

## Akzeptanzkriterien

- [ ] `registry.yaml`/`registry.schema.yaml` vorhanden (geliefert, hier nur
      bestätigen)
- [ ] `registry.py`: `resolve_base` fail-closed bei unbekannter Maschine,
      `CCB_PROJECT_BASE`-Override funktioniert
- [ ] `project_local_path` fail-soft (nie Absturz wegen einem Projekt)
- [ ] `last_transition_at` liefert korrekten Zeitpunkt
- [ ] `ccb board` zeigt beide Wartezustände projektübergreifend, sortiert,
      mit `depends_on`-Hinweis, fail-soft bei fehlendem Profil
- [ ] `ccb commands` zeigt Befehlsreferenz, fail-closed bei unbekannter
      Maschine ohne Override
- [ ] alle Tests grün; Pflicht-Footer

## Nächster Auftrag

Noch offen — hängt davon ab, wie sich Board + Befehlsreferenz im Alltag
bewähren (s. offene Zielfragen aus CCB-UEBERGABE.md Abschnitt 7a: API-
Vollautomatik vs. dauerhafter manueller Dirigent). Nach BRIDGE-016 zunächst
eine Weile im echten Betrieb nutzen, bevor der nächste Schritt festgelegt
wird.
