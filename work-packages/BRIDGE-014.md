# BRIDGE-014 — Übergabe-Wartezustände + automatischer Auto-Chain (leichter Weg)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-014 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-004, BRIDGE-009, BRIDGE-013 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Kontext (Richtungswechsel, s. CCB-UEBERGABE.md Abschnitt 6)

Das eigentliche Ziel ist ein projektübergreifendes Copy-Paste-Board (BRIDGE-015),
das anzeigt: "Auftrag X wartet darauf, kopiert zu werden." Voraussetzung dafür:
die zwei Kopierrichtungen müssen als echte Zustände im Repo stehen, nicht nur
gedacht sein. BRIDGE-014 liefert genau diese zwei Zustände — **entschieden: 2,
nicht 3** (das vorhandene REVIEW_REQUIRED/APPROVAL_REQUIRED deckt die fachliche
Freigabe bereits ab, ein dritter Wartezustand wäre redundant).

**Ebenfalls entschieden:** die Auftragsentstehung/-übergabe soll so automatisch
wie möglich passieren — der Mensch soll dafür keine zusätzlichen Befehle lernen
müssen. Deshalb werden die neuen Zustände wo immer möglich **automatisch als
Teil bestehender Befehle** durchlaufen (Auto-Chain-Prinzip, wie es `runner.start()`
für CREATED→READY→CLAIMED→RUNNING bereits vormacht), nicht über einen neuen
manuellen Zwischenschritt.

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/state-model.yaml` — um `WAITING_FOR_HANDOFF_TO_EXECUTOR` und
  `WAITING_FOR_COPY_TO_CONTROL` erweitert (neue states + transitions). Die
  alten direkten Kanten (`READY→CLAIMED`, `COMPLETED→REVIEW_REQUIRED`) bleiben
  zusätzlich bestehen (Abwärtskompatibilität, spätere Stufe-3-Automatik ohne
  Kopierschritt).
- `schemas/audit-event-map.yaml` — zwei neue Einträge in `by_new_state`:
  `WAITING_FOR_HANDOFF_TO_EXECUTOR → TASK_WAITING_FOR_HANDOFF`,
  `WAITING_FOR_COPY_TO_CONTROL → TASK_WAITING_FOR_COPY`.

Bereits gegen die bestehende Testsuite geprüft (109/109 grün, keine Regression)
und die vier neuen Übergänge funktional verifiziert.

## Von Claude Code umzusetzen

### 1) `src/bridge/cli.py` — `_cmd_task`, Zweig `"create"`: Auto-Chain nach WAITING_FOR_HANDOFF_TO_EXECUTOR

Nach dem bestehenden `store.create_task(args.path)` zusätzlich automatisch
zwei Schritte weiterschalten, damit ein frisch angelegter Auftrag sofort
board-sichtbar ist, ohne dass der Nutzer etwas Zusätzliches eingeben muss:

```python
if args.task_cmd == "create":
    doc = store.create_task(args.path)
    actor = doc.get("created_by", "unknown")
    store.set_status(doc["bridge_task_id"], "READY", actor, None,
                      reason="auto: Auftrag angelegt")
    doc = store.set_status(doc["bridge_task_id"], "WAITING_FOR_HANDOFF_TO_EXECUTOR",
                            actor, None,
                            reason="auto: wartet auf Weitergabe an Executor")
    print(f"OK: {doc['bridge_task_id']} angelegt (status={doc['new_state']})")
    return 0
```

Prüfe das exakte Rückgabeformat von `store.set_status` (Event-dict mit
`new_state`, siehe bestehende Nutzung in `_cmd_task`, Zweig `set-status`) und
passe die Ausgabezeile entsprechend an — es muss weiterhin
`OK: <id> angelegt (status=WAITING_FOR_HANDOFF_TO_EXECUTOR)` ausgegeben werden.

### 2) `src/bridge/runner.py` — `start()`: neuen Zustand in die Kette aufnehmen

```python
_START_CHAIN = ("CREATED", "READY", "WAITING_FOR_HANDOFF_TO_EXECUTOR", "CLAIMED", "RUNNING")
```

`_START_FROM = _START_CHAIN[:-1]` bleibt wie es ist (wird automatisch um den
neuen Zustand erweitert). Dadurch akzeptiert `run start` jetzt auch einen
Auftrag im Zustand `WAITING_FOR_HANDOFF_TO_EXECUTOR` als gültigen Startpunkt
(das ist der Normalfall: Mensch hat kopiert, Executor startet) — und schaltet,
falls ein Auftrag ausnahmsweise noch bei READY oder CREATED steht, automatisch
durch alle fehlenden Zwischenschritte (bestehendes Verhalten, nur um ein Glied
verlängert).

### 3) `src/bridge/runner.py` — `finish()`: Auto-Chain nach WAITING_FOR_COPY_TO_CONTROL, NUR bei COMPLETED

Bewusste Scope-Entscheidung: nur der Erfolgspfad (`status == "COMPLETED"`)
bekommt den automatischen Wartezustand. `FAILED`, `BLOCKED`, `REVIEW_REQUIRED`,
`APPROVAL_REQUIRED` bleiben unverändert (dort ist ohnehin sofort menschliche/
Steuerchat-Aufmerksamkeit nötig, kein zusätzlicher Wartepunkt nötig). Diese
Einschränkung kann später erweitert werden, falls sich das im Alltag als zu
eng erweist.

```python
def finish(store, task_id, status, *, draft=None, base_head=None, actor,
           machine=None, git_info_fn=None, now=None, **prov):
    ...  # bestehender Code bis einschließlich der bestehenden
    event = store.set_status(task_id, status, actor, machine,
                             reason=f"runner: finish -> {status}")
    if status == "COMPLETED":
        event = store.set_status(task_id, "WAITING_FOR_COPY_TO_CONTROL", actor, machine,
                                 reason="auto: wartet auf Kopie in den Steuerchat")
    return result, event
```

### 4) `src/bridge/cli.py` — neuer Komfort-Befehl `task copied` (leichter Weg für den Menschen)

Damit der Mensch nach dem Einfügen in den Steuerchat nicht den generischen
`set-status`-Befehl mit Zustandsnamen tippen muss:

```python
tsub.add_parser("copied", help="Ergebnis wurde in den Steuerchat kopiert (-> REVIEW_REQUIRED)") \
    .add_argument("task_id")
# gleiche Zeile noch: .add_argument("--actor", required=True)
```

In `_cmd_task`:
```python
if args.task_cmd == "copied":
    event = store.set_status(args.task_id, "REVIEW_REQUIRED", args.actor, None,
                             reason="Ergebnis in Steuerchat kopiert")
    print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']} "
          f"({event['event_type']})")
    return 0
```

Fail-closed bleibt automatisch erhalten: `store.set_status` lehnt den Aufruf
ab, wenn der Auftrag nicht in `WAITING_FOR_COPY_TO_CONTROL` steht (State-Machine
prüft das ohnehin schon zentral) — kein Sonderfall nötig.

### 5) Tests

`tests/test_runner.py` ergänzen:
- `task create` (bzw. `store.create_task` + der neue Auto-Chain-Aufruf) landet
  direkt bei `WAITING_FOR_HANDOFF_TO_EXECUTOR`, nicht bei `CREATED`/`READY`.
- `run start` funktioniert unverändert aus `WAITING_FOR_HANDOFF_TO_EXECUTOR`
  heraus (bestehendes Verhalten, neuer Startpunkt).
- `run finish(status="COMPLETED")` landet bei `WAITING_FOR_COPY_TO_CONTROL`,
  NICHT bei `COMPLETED` (der Rückgabewert/das Audit-Event muss das zeigen).
- `run finish(status="FAILED")` bleibt unverändert bei `FAILED` (kein Auto-Chain).
- neuer Komfort-Befehl `task copied`: aus `WAITING_FOR_COPY_TO_CONTROL` heraus
  → `REVIEW_REQUIRED`; aus jedem anderen Zustand heraus → Fehler (fail-closed).

`tests/test_state_machine.py` ergänzen (falls dort Übergänge einzeln geprüft
werden, analog zu bestehenden Tests):
- die vier neuen Übergänge sind erlaubt.
- ein unerlaubter Sprung, z. B. `WAITING_FOR_HANDOFF_TO_EXECUTOR → RUNNING`,
  wird abgelehnt.

### 6) Abschluss

- `python -m unittest discover -s tests` grün (alle bisherigen 109 + neue).
- `work-packages/BRIDGE-014.md`: Akzeptanzkriterien `[ ]` → `[x]` abhaken.
- Pflicht-Footer: `Auftrag: BRIDGE-014 / Lauf: RUN-01 / Status: ...`

## Scope

**Enthalten:** zwei neue Wartezustände + Übergänge (geliefert), Audit-Mapping
(geliefert), Auto-Chain in `task create` und `run finish(COMPLETED)`,
erweiterte Startkette in `run start`, neuer Komfort-Befehl `task copied`,
Tests.

**NICHT enthalten:**
- das Terminal-Board selbst (Anzeige über alle Projekte) → BRIDGE-015.
- Auto-Chain für `FAILED`/`BLOCKED`/`REVIEW_REQUIRED`/`APPROVAL_REQUIRED` als
  Finish-Ziel (bewusst ausgeklammert, s. o.).
- Wartezustand beim Resume-Pfad (`resume()` bleibt unverändert) — falls sich
  das im Alltag als Lücke zeigt, eigenes kleines Arbeitspaket.

## Akzeptanzkriterien

- [x] `WAITING_FOR_HANDOFF_TO_EXECUTOR` und `WAITING_FOR_COPY_TO_CONTROL` im
      Zustandsmodell (geliefert, hier nur bestätigen)
- [x] `task create` landet automatisch bei `WAITING_FOR_HANDOFF_TO_EXECUTOR`
- [x] `run start` funktioniert aus `WAITING_FOR_HANDOFF_TO_EXECUTOR` heraus
- [x] `run finish --status COMPLETED` landet automatisch bei
      `WAITING_FOR_COPY_TO_CONTROL`
- [x] `run finish` mit jedem anderen Status bleibt unverändert (kein Auto-Chain)
- [x] neuer Befehl `task copied` funktioniert und ist fail-closed
- [x] alle Tests grün; Pflicht-Footer am Ende

## Umsetzungsnotiz (RUN-01)

Zusätzlich zu `state-model.yaml`/`audit-event-map.yaml` (von der Steuerebene
geliefert) mussten die **Enums in zwei weiteren Schemadateien** um die zwei
neuen Zustände bzw. Ereignistypen ergänzt werden, sonst wäre jede
`set_status`-/`import_result`-Validierung fail-closed abgebrochen:

- `schemas/task.schema.yaml` — `status`-Enum (+ 2 Zustände)
- `schemas/audit-event.schema.yaml` — `event_type`-Enum (+ `TASK_WAITING_FOR_HANDOFF`,
  `TASK_WAITING_FOR_COPY`) sowie `old_state`/`new_state`-Enums (+ 2 Zustände)

Betroffene Bestandstests an das neue Auto-Chain-Verhalten angepasst
(`test_cli.py`, `test_runner.py`). Gesamt 117 Tests grün (109 + 8 neue).

## Nächster Auftrag

**BRIDGE-015 — Projekt-Registry + Copy-Paste-Board (Terminal).** Zeigt
projektübergreifend alle Aufträge in den zwei neuen Wartezuständen (sortiert
nach Auftragsnummer + `depends_on`) UND hält zusätzlich die gängigsten Befehle
griffbereit (Bridge starten, Handover-Check vorbereiten, u. a.) — Umfang wird
im nächsten Arbeitspaket präzisiert.
