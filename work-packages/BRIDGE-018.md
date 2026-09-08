# BRIDGE-018 — 'bridge board --watch'

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0018 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-0016 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Kontext

`bridge board` (BRIDGE-016) ist bisher ein Einmal-Schnappschuss — man muss
ihn jedes Mal manuell neu aufrufen, um zu sehen, ob sich etwas geändert hat.
Gewünscht: ein Modus, der in einem eigenen Terminalfenster dauerhaft läuft
und sich selbst aktualisiert — nach demselben bewährten Muster wie
`watcher.loop()` (BRIDGE-008), das es für den Watcher schon gibt.

`tasks/BRIDGE-0018/task.yaml` liegt bereits im Repo (geliefert, validiert).

## Von Claude Code umzusetzen

### 1) Auftrag anlegen und starten (wie bei BRIDGE-017)

```
bridge task create tasks/BRIDGE-0018/task.yaml
bridge run start BRIDGE-0018 --actor claude-code
```

### 2) Board-Rendering von der Anzeige trennen (kleine Refaktorierung)

Falls `board` bisher Datenermittlung und `print`-Ausgabe in einer Funktion
vermischt: in zwei Teile trennen — eine Funktion, die die Zeilen (Liste von
Dicts oder Tupeln) liefert, und eine, die daraus den Tabellentext baut. Damit
kann sowohl der Einmal-Aufruf als auch der neue `--watch`-Modus dieselbe
Logik nutzen, ohne Duplikation.

### 3) `--watch`-Flag für `board`

```
bridge board [--machine NAME] [--watch] [--interval SEKUNDEN]
```

- `--interval` nur zusammen mit `--watch` sinnvoll; Default z. B. `15.0`.
- Ohne `--watch`: unverändertes bisheriges Verhalten (ein Aufruf, ein Exit).
- Mit `--watch`: Schleife nach demselben Muster wie `watcher.loop()` —
  **kein Bildschirm-Löschen** (fragil über verschiedene Windows-Terminals
  hinweg), stattdessen vor jeder Aktualisierung eine Trennzeile mit
  Zeitstempel ausgeben, z. B.:

  ```
  === bridge board (Aktualisiert: 2026-09-08T12:00:03Z) ===
  #  Projekt  Auftrag      Richtung                Wartet seit
  1  DORF     DORF-0015    Executor -> Steuerchat   2h 14m
  ```

  Interner Aufbau wie `watcher.loop()`: eine Funktion mit `max_iterations`
  und `sleep`-Parameter (Default `time.sleep`), damit Tests nicht wirklich
  warten müssen — exakt dasselbe Test-Pattern wie in `test_watcher.py`
  bereits verwendet.
- **Read-only:** `--watch` liest nur, schreibt nichts, kein `--apply`-
  Äquivalent nötig (anders als beim Watcher) — das ist hier bewusst einfacher.
- Beendigung: `Ctrl+C` (`KeyboardInterrupt`) sauber abfangen und mit
  Exit-Code 0 beenden, keine hässliche Traceback-Ausgabe für den Nutzer.

### 4) Tests

- Neue Tests analog zu den bestehenden `watcher.loop()`-Tests: `--watch`
  mit `max_iterations=3` (nur intern testbar, kein CLI-Flag dafür nötig)
  ruft die Board-Logik dreimal auf, `sleep` wird gemockt (kein echtes
  Warten in Tests).
- `Ctrl+C`/`KeyboardInterrupt` während der Schleife führt zu sauberem
  Exit-Code 0, kein unbehandelter Traceback.
- Ohne `--watch` bleibt das bestehende Verhalten unverändert (Regressionstest).

### 5) Abschluss über die Bridge selbst

```
python -m unittest discover -s tests
bridge run finish BRIDGE-0018 --status COMPLETED --actor claude-code
bridge board
```

`bridge board`-Ausgabe (zeigt jetzt sowohl BRIDGE-0017 als auch BRIDGE-0018
in `WAITING_FOR_COPY_TO_CONTROL`, falls BRIDGE-0017 zu diesem Zeitpunkt noch
nicht kopiert wurde) in die Antwort mit aufnehmen.

work-packages/BRIDGE-018.md: Akzeptanzkriterien `[ ]` → `[x]` abhaken.

Pflicht-Footer: `Auftrag: BRIDGE-018 / Lauf: RUN-01 / Status: ...`

## Akzeptanzkriterien

- [x] `bridge task create` + `run start` für BRIDGE-0018 tatsächlich
      ausgeführt
- [x] `--watch`/`--interval` implementiert, kein Bildschirm-Löschen, dafür
      Zeitstempel pro Aktualisierung
- [x] `Ctrl+C` sauber abgefangen (Exit 0, kein Traceback)
- [x] Board-Logik wiederverwendet (keine Duplikation zwischen Einmal- und
      Watch-Modus)
- [x] Tests mit gemocktem `sleep`/`max_iterations`, keine echten Wartezeiten
      in der Testsuite
- [x] `bridge run finish` tatsächlich ausgeführt, `bridge board`-Ausgabe in
      der Antwort
- [x] alle Tests grün; Pflicht-Footer

## Nächster Auftrag

Noch offen — Board, Befehlsreferenz und Watch-Modus jetzt im Alltag nutzen.
