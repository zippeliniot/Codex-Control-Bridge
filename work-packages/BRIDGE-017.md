# BRIDGE-017 — Komfortbefehl 'task archive'

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0017 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-0016 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Kontext

**Erstes Paket, das über die Bridge selbst läuft.** Bisher liefen alle 16
Pakete nur als `work-packages/*.md` (reine Doku) — `tasks/` war leer, das
Board konnte für dieses Projekt selbst nie etwas anzeigen. Entschieden:
alte Pakete (001–016) bleiben historisch nur als Dokument, aber ab jetzt
läuft jedes neue Paket zusätzlich als echter `bridge_task` durch den Store.

`tasks/BRIDGE-0017/task.yaml` liegt bereits im Repo (von der Steuerebene
geliefert, gegen das Schema validiert) — das ist der Auftrag selbst als
Bridge-Objekt.

## Von Claude Code umzusetzen

### 1) Auftrag anlegen (allererster Schritt, vor jeder Code-Änderung)

```
bridge task create tasks/BRIDGE-0017/task.yaml
```

Das setzt ihn automatisch nach `WAITING_FOR_HANDOFF_TO_EXECUTOR` (BRIDGE-014).
Danach:

```
bridge run start BRIDGE-0017 --actor claude-code
```

### 2) `src/bridge/cli.py`: neuer Unterbefehl `task archive`

Analog zu `task copied` (BRIDGE-014), aber **ohne** dessen expliziten
Ausgangszustands-Check — der ist dort nötig, weil `task copied` ein enges
semantisches Versprechen hat (nur nach tatsächlichem Kopieren). `task archive`
ist bewusst allgemeiner ("dieser Auftrag ist erledigt, egal aus welchem
Zustand") — die bestehende Zustandstabelle regelt bereits korrekt, aus
welchen Zuständen `ARCHIVED` erreichbar ist (z. B. nicht aus `RUNNING` —
das ist so gewollt, kein Sonderfall nötig).

```python
tsub.add_parser("archive", help="Auftrag abschliessen (-> ARCHIVED)") \
    .add_argument("task_id")
# gleiche Zeile: .add_argument("--actor", required=True)
# gleiche Zeile: .add_argument("--reason", default=None)
```

In `_cmd_task`:
```python
if args.task_cmd == "archive":
    reason = args.reason or "Auftrag abgeschlossen"
    event = store.set_status(args.task_id, "ARCHIVED", args.actor, None, reason=reason)
    print(f"OK: {args.task_id} {event['old_state']} -> {event['new_state']} "
          f"({event['event_type']})")
    return 0
```

### 3) Tests

`tests/test_cli.py` ergänzen: `task archive` funktioniert aus einem Zustand,
der `ARCHIVED` erlaubt (z. B. `REVIEW_REQUIRED`); schlägt korrekt fehl (über
die bestehende Zustandstabelle, kein neuer Code dafür nötig) aus einem
Zustand, der es nicht erlaubt (z. B. `RUNNING`).

### 4) Abschluss dieses Auftrags über die Bridge selbst (nicht nur Footer!)

Das ist der eigentliche Zweck dieses Pakets — bitte diesmal wirklich
ausführen, nicht nur den Footer schreiben:

```
python -m unittest discover -s tests
bridge run finish BRIDGE-0017 --status COMPLETED --actor claude-code
```

Das setzt automatisch `WAITING_FOR_COPY_TO_CONTROL` (BRIDGE-014). Danach
`bridge board` aufrufen und die Ausgabe in deine Antwort mit aufnehmen —
das ist der Beweis, dass der Kreislauf diesmal wirklich lief.

work-packages/BRIDGE-017.md: Akzeptanzkriterien `[ ]` → `[x]` abhaken.

Pflicht-Footer: `Auftrag: BRIDGE-017 / Lauf: RUN-01 / Status: ...`

## Akzeptanzkriterien

- [x] `bridge task create` ausgeführt (nicht nur Doku geschrieben) — über
      Staging-Datei `tasks/incoming/BRIDGE-0017.yaml` (danach wieder entfernt),
      da die Spec bereits am Store-Ziel lag und `create_task` fail-closed nicht
      überschreibt; danach `bridge run start` → `RUNNING`
- [x] `task archive` implementiert, kein Sonderfall-Check (Zustandstabelle
      reicht)
- [x] Tests für Erfolg und Fehlschlag vorhanden
- [x] `bridge run finish --status COMPLETED` tatsächlich ausgeführt am Ende
- [x] `bridge board`-Ausgabe zeigt BRIDGE-0017 in `WAITING_FOR_COPY_TO_CONTROL`
      (in der Antwort mit angeben)
- [x] alle Tests grün (148); Pflicht-Footer

## Nächster Auftrag

Board + Befehlsreferenz jetzt im echten Alltag nutzen. Kein fest geplantes
BRIDGE-018 — nächster Schritt hängt davon ab, was sich in der Praxis zeigt.
