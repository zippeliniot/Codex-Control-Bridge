# BRIDGE-008 — Watcher (Erkennung & automatische Weiterführung)

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-008 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-004, BRIDGE-005, BRIDGE-006 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code (DES11) |

## Auftrag

Ein Watcher beobachtet den Repo-Zustand, erkennt (a) fertige Ergebnisse und
(b) steckengebliebene Läufe (toter Heartbeat) und führt den Auftragszustand
automatisch weiter — nur mit ausdrücklicher Freigabe, nur erlaubte Übergänge,
niemals Git-Aktionen.

## Sicherheits-Leitplanken (verbindlich)

1. **Schreiben ist opt-in.** Ohne `--apply` nur melden (Trockenlauf). Mit
   `--apply` werden Übergänge über `Store.set_status` gesetzt.
2. **Nur Policy-Übergänge.** Erlaubte Übergänge ausschließlich aus
   `schemas/watcher-policy.yaml`; jeder Übergang zusätzlich durch den
   BRIDGE-004-Validator geprüft. Kein Übergang, den das state-model verbietet.
3. **Nie Git.** Kein commit/push/merge. Der Watcher ändert nur `task.yaml` +
   Auditspur; Committen/Pushen bleibt beim Menschen.
4. **Fail-closed.** Mehrdeutige Lage, kaputter Heartbeat, nicht erlaubter
   Übergang → nichts tun, melden.
5. **Kein Result wird erfunden.** Bei totem Heartbeat setzt der Watcher nur den
   Auftragsstatus (+ Audit-Reason), er schreibt KEIN result.yaml.

## Bereits von der Steuerebene geliefert (NICHT verändern)

- `schemas/heartbeat.schema.yaml` — Heartbeat-Format.
- `schemas/watcher-policy.yaml` — SSOT: Timeout + erlaubte Automatik-Übergänge.
- `src/bridge/store.py` (`load_task`, `set_status`, `next_run_id`, `validate`),
  `src/bridge/state_machine.py`.

## Von Claude Code umzusetzen (keine neue Abhängigkeit, nur stdlib)

### Heartbeat `src/bridge/heartbeat.py`
- `heartbeat_path(root, id, run_id)` → `results/<id>/RUN-<yy>/heartbeat.json`.
- `beat(root, id, run_id, actor=None, machine=None)` — schreibt/aktualisiert die
  Heartbeat-Datei mit `last_seen = jetzt` (UTC RFC 3339), validiert gegen
  `heartbeat.schema.yaml`. (Automatisches, periodisches Schlagen ist Sache des
  Runners in BRIDGE-009.)
- `read_heartbeat(root, id, run_id)` → dict oder None; kaputte Datei → Fehler.

### Watcher `src/bridge/watcher.py`
- `load_policy(schema_dir)` — liest `watcher-policy.yaml`.
- `scan(store, policy, *, now=<utc-jetzt>) -> list[Finding]`:
  Für jeden Auftrag in `eligible_from_status`:
  - **Ergebnis fertig?** existiert `results/<id>/<letzter RUN>/result.yaml` mit
    Status S und `policy.on_result_status[S]` ist ein von hier erlaubter
    Übergang → Finding(kind="result", target=…).
  - **Heartbeat tot?** `now - last_seen > heartbeat_timeout_seconds` (oder
    Heartbeat fehlt jenseits einer Karenz) → Finding(kind="stale",
    target=on_stale_heartbeat.to_status, reason=…).
  - Findet beides zu, hat „result" Vorrang (der Lauf hat ein Ergebnis geliefert).
  - `now` ist Parameter → Tests injizieren die Zeit (kein echtes Warten).
- `apply(store, findings, actor, machine=None) -> list[Applied]`:
  setzt je Finding `store.set_status(id, target, actor, machine, reason)` — nur
  wenn der Übergang erlaubt ist; sonst überspringen und vermerken.
- `run_once(store, policy, *, apply=False, actor=None, now=…)` — scan (+ optional apply).
- `loop(store, policy, *, interval, apply=False, actor=None, max_iterations=None)` —
  ruft `run_once` wiederholt; `max_iterations` nur für Tests (sonst endlos).

### CLI-Erweiterung `src/bridge/cli.py`
- `watch scan [--apply] [--actor <a>] [--machine <m>] [--task <BRIDGE-id>]`
- `watch loop --interval <sek> [--apply] [--actor <a>] [--machine <m>]`
- `watch heartbeat <BRIDGE-id> <RUN-YY> [--actor <a>] [--machine <m>]`
  (schreibt/aktualisiert den Heartbeat)
- `--apply` erfordert `--actor` (wer den Wechsel verantwortet), sonst Exit 2.

### Tests `tests/test_watcher.py` (stdlib unittest, hermetisch, Zeit injiziert)
- fertiges COMPLETED-Ergebnis + Task RUNNING → scan meldet Übergang;
  mit apply → Task COMPLETED + Audit `TASK_COMPLETED`
- ohne `--apply` wird NICHTS geschrieben (Trockenlauf)
- Heartbeat frisch (now knapp) → kein stale-Finding
- Heartbeat alt (now > timeout) + Task RUNNING → stale-Finding; mit apply →
  Task INTERRUPTED + Audit-Reason gesetzt; KEIN result.yaml erzeugt
- Ergebnis hat Vorrang vor stale, wenn beides zutrifft
- nicht erlaubter Zielübergang → übersprungen, nichts geschrieben (fail-closed)
- kaputte Heartbeat-Datei → Fehler (fail-closed)
- `beat()` schreibt schema-konformen Heartbeat; `read_heartbeat` liest ihn
- `loop(max_iterations=2)` ruft scan zweimal (kein echtes Sleep im Test)

### Abschluss
- `python -m unittest discover -s tests` grün (alle bisherigen + neue).
- Pflicht-Footer (`BRIDGE-008` + `RUN-YY` + Status).

## Scope

**Enthalten:** heartbeat.schema.yaml + watcher-policy.yaml (geliefert),
`src/bridge/heartbeat.py`, `src/bridge/watcher.py`, CLI-Erweiterung `watch`,
`tests/test_watcher.py`, README-Nachzug, dieses Arbeitspaket.

**NICHT enthalten:** automatisches periodisches Schlagen des Heartbeats durch
einen lebenden Executor → Runner (BRIDGE-009); Resume-Orchestrierung → BRIDGE-009.

## Akzeptanzkriterien

- [x] scan erkennt fertige Ergebnisse und tote Heartbeats
- [x] Schreiben nur mit `--apply`; ohne apply reiner Trockenlauf
- [x] nur Policy-Übergänge, zusätzlich durch state_machine geprüft
- [x] toter Heartbeat setzt nur Status (+Audit), erzeugt kein result.yaml
- [x] Zeit injizierbar; Tests hermetisch ohne echtes Warten
- [x] Watcher führt nie Git-Aktionen aus
- [x] alle Tests grün; Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-009 — Runner & Resume-Orchestrierung** (Heartbeat automatisch schlagen,
Lauf ausführen/fortsetzen).
