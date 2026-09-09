# BRIDGE-022 — `runner.resume()` um `REVIEW_REQUIRED` erweitern

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-0022 |
| project_id | codex-control-bridge |
| task_class | BUGFIX |
| depends_on | (keine) |
| permission | WORKTREE_WRITE, TEST_EXECUTION, GIT_PUSH |
| executor | claude-code |
| Modell/Denkstufe | Claude Code, Denkstufe LOW-MEDIUM (Ein-Zeilen-Fix an einer bereits vollständig getesteten Funktion, plus Tests — kein neues Konzept, keine Architekturentscheidung.) |

## Kontext

Fund aus BRIDGE-0020 RUN-02 (Claude Code, korrektes Fail-closed nach
`CLAUDE.md` Regel 5, keine Improvisation): `bridge run resume` scheitert an
einem Auftrag im Zustand `REVIEW_REQUIRED`, obwohl `schemas/state-model.yaml`
— die einzige maßgebliche Quelle für Übergänge (`state_machine.py` liest
ausschließlich diese Datei) — den Übergang `REVIEW_REQUIRED -> RUNNING`
ausdrücklich erlaubt:

```
REVIEW_REQUIRED:  [COMPLETED, APPROVAL_REQUIRED, RUNNING, FAILED, BLOCKED, ARCHIVED]
```

`src/bridge/runner.py` bildet diesen legalen Übergang aber nicht ab:

```python
_RESUME_FROM = ("INTERRUPTED", "WAITING_FOR_RESUME")
```

Das ist eine Lücke im Work-Package `BRIDGE-020.md`, die ich (Steuerchat)
verursacht habe — ich bin beim Schreiben der Spec fälschlich davon
ausgegangen, `run resume` decke jeden im State-Model erlaubten Rücksprung
nach `RUNNING` ab, ohne das gegen `runner.py` zu prüfen. Dieser Auftrag
behebt die Lücke im Code, nicht nur die Doku.

**Bewusst nicht mit im Scope:** `APPROVAL_REQUIRED -> RUNNING` ist laut
State-Model ebenfalls erlaubt und hat dieselbe Lücke — aber dafür gibt es
aktuell keinen konkreten Bedarf (kein Auftrag steckt gerade dort fest).
Nicht vorsorglich mit erledigen, um den Fix klein und den Grund
nachvollziehbar zu halten. Falls später gebraucht, eigener kleiner Auftrag
nach demselben Muster.

## Von Claude Code umzusetzen

1. Auftrag anlegen und starten:
   ```
   bridge task create tasks/incoming/BRIDGE-0022.yaml
   bridge run start BRIDGE-0022 --actor claude-code
   ```
   (Staging-Datei danach löschen.)

2. `src/bridge/runner.py`: `_RESUME_FROM` um `"REVIEW_REQUIRED"` ergänzen:
   ```python
   _RESUME_FROM = ("INTERRUPTED", "WAITING_FOR_RESUME", "REVIEW_REQUIRED")
   ```
   Der bestehende Funktionskörper von `resume()` muss dafür **nicht**
   geändert werden — er prüft nur `status in _RESUME_FROM`, geht bei
   `INTERRUPTED` über den Zwischenschritt `WAITING_FOR_RESUME`, sonst direkt
   auf `RUNNING`. Für `REVIEW_REQUIRED` greift automatisch der direkte Ast
   (`store.set_status(task_id, "RUNNING", ...)`), was exakt dem in
   `state-model.yaml` erlaubten Übergang entspricht. Nur die Fehlermeldung
   im `RunnerError`-Fall passt sich automatisch an (baut auf
   `_RESUME_FROM` auf), keine separate Textänderung nötig.

3. Docstring von `resume()` (aktuell: `"""INTERRUPTED/WAITING_FOR_RESUME ->
   RUNNING (ein Schritt), neuer RUN, frischer Heartbeat."""`) entsprechend
   um `REVIEW_REQUIRED` ergänzen, damit er den Code nicht mehr falsch
   beschreibt.

4. Tests (`tests/test_runner.py` oder wo die bestehenden `resume()`-Tests
   liegen):
   - Neuer Test: Auftrag in `REVIEW_REQUIRED` → `runner.resume(...)` →
     Status `RUNNING`, neue `run_id` (z. B. `RUN-02`, wenn `RUN-01` bereits
     existierte), frischer Heartbeat wird angelegt (gleiches Muster wie der
     bestehende `INTERRUPTED`-Test, nur anderer Ausgangszustand).
   - Regressionstest: `resume()` aus einem **nicht** erlaubten Zustand
     (z. B. weiterhin `WAITING_FOR_COPY_TO_CONTROL`) liefert weiterhin
     `RunnerError` — die Erweiterung darf nicht versehentlich zu freizügig
     werden.
   - Bestehende `INTERRUPTED`/`WAITING_FOR_RESUME`-Tests bleiben unverändert
     grün (keine Verhaltensänderung für diese beiden Fälle).

5. `work-packages/BRIDGE-020.md` **nicht** in diesem Auftrag anfassen — das
   macht der Steuerchat separat, sobald dieser Fix gepusht und verifiziert
   ist (Korrektur des RUN-02-Wiedereinstiegs für den bereits laufenden
   BRIDGE-0020).

6. Da dieser Auftrag `GIT_PUSH` im Berechtigungsprofil trägt: Nach
   `run finish` selbst `git push` ausführen (Ask-Bestätigung in Claude Code
   bestätigen). `--force`-Push bleibt in jedem Fall verboten.

7. Pflicht-Footer + Abschluss:
   ```
   bridge run finish BRIDGE-0022 --status COMPLETED --actor claude-code \
     --summary "runner._RESUME_FROM um REVIEW_REQUIRED erweitert (state-model.yaml erlaubt REVIEW_REQUIRED->RUNNING, runner.py bildete es nicht ab), Tests fuer den neuen Pfad + Regressionstest fuer weiterhin verbotene Zustaende."
   git push
   ```
   `Auftrag: BRIDGE-0022 / Lauf: RUN-01 / Status: COMPLETED`

## Akzeptanzkriterien

- [x] `bridge run resume BRIDGE-0020 --actor claude-code` funktioniert jetzt
      aus dem Zustand `REVIEW_REQUIRED` (manueller Nachtest gegen den
      echten BRIDGE-0020-Auftrag nach diesem Fix, nicht nur Unit-Test).
- [x] `_RESUME_FROM` enthält `REVIEW_REQUIRED` zusätzlich zu den
      bisherigen zwei Werten, keine weiteren Zustände.
- [x] `resume()` aus nicht erlaubten Zuständen scheitert weiterhin mit
      `RunnerError` (Regressionstest vorhanden und grün).
- [x] Bestehendes Verhalten für `INTERRUPTED`/`WAITING_FOR_RESUME`
      unverändert.
- [x] Alle Tests grün (bestehende Basis + neue), frischer Klon verifiziert.
- [x] Commit gepusht (dieser Auftrag trägt `GIT_PUSH`).
