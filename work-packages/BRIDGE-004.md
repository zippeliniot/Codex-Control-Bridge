# BRIDGE-004 — Zustandsmodell, Übergänge & Übergangs-Validator

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-004 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-002, BRIDGE-003 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code (HAM11) |

## Auftrag

Das Zustandsmodell (Konzept-Abschnitt 5 + 7) verbindlich festlegen und einen
**ausführbaren Übergangs-Validator** bereitstellen, der prüft, ob ein
Statuswechsel erlaubt ist. Zusätzlich das Audit-Ereignisformat (Abschnitt 10)
als Schema.

## Bereits von der Steuerebene geliefert (NICHT verändern)

Diese Dateien sind die maßgebliche Quelle und liegen bereits im Repo:

- `schemas/state-model.yaml` — **SSOT** der Zustände und erlaubten Übergänge.
- `schemas/audit-event.schema.yaml` — Schema eines Audit-Ereignisses.

Der Validator liest die Übergänge **ausschließlich** aus `state-model.yaml`.
Die Tabelle wird **nicht** im Code dupliziert oder hartkodiert.

## Von Claude Code umzusetzen (Code-Logik)

### Sprache & Abhängigkeit
- **Python 3.** Erste Handlung: `python --version` und `pip --version` prüfen.
  Ist Python nicht vorhanden → **fail-closed**: anhalten und melden, NICHT
  selbst installieren (Systemänderung nur durch den Menschen).
- Einzige Laufzeitabhängigkeit: **PyYAML**. Lege `requirements.txt` mit
  `pyyaml` an; installiere es NUR nach Zustimmung (`ask`-Regel greift ohnehin
  nicht für pip, daher vorher fragen).

### Dateien
1. `src/bridge/__init__.py` — leer (Paketmarker).
2. `src/bridge/state_machine.py` — der Validator. Anforderungen:
   - `load_model(path="schemas/state-model.yaml") -> dict` lädt das Modell.
   - `STATES`, `TERMINAL_STATES`, `TRANSITIONS` aus dem Modell ableiten.
   - `is_allowed(from_state, to_state) -> bool`:
     True nur, wenn beide Zustände bekannt sind UND `to_state` in
     `TRANSITIONS[from_state]` steht. Sonst False.
   - `assert_transition(from_state, to_state) -> None`:
     wirft `TransitionError` (eigene Exception) mit klarer Meldung, wenn nicht
     erlaubt. Unbekannte Zustände → **fail-closed** (Fehler, nie stillschweigend
     erlauben).
   - Fehlende/fehlerhafte Modelldatei → klarer Fehler (fail-closed).
   - CLI: Aufruf `python src/bridge/state_machine.py <FROM> <TO>` gibt
     `ALLOWED` (Exit 0) oder `DENIED: <grund>` (Exit 1) aus.
3. `tests/test_state_machine.py` — mit dem **stdlib-`unittest`** (kein pytest),
   damit keine zusätzliche Testabhängigkeit nötig ist. Pflicht-Testfälle:
   - erlaubter Übergang `CREATED -> READY` ist True
   - unerlaubter Übergang `CREATED -> RUNNING` ist False
   - unbekannter Ausgangszustand → fail-closed (False bzw. Fehler)
   - unbekannter Zielzustand → fail-closed
   - `ARCHIVED` ist terminal (keine erlaubten Ziele)
   - jeder Zustand aus `STATES` hat einen Eintrag in `TRANSITIONS`
   - jedes Ziel in `TRANSITIONS` ist ein bekannter Zustand
   - `assert_transition` wirft bei unerlaubtem Übergang `TransitionError`

### Abschluss
- Alle Tests grün: `python -m unittest discover -s tests` muss ohne Fehler laufen.
- Am Ende den **Pflicht-Footer** ausgeben (siehe CLAUDE.md): `BRIDGE-004` + `RUN-YY` + Status.

## Scope

**Enthalten:** state-model.yaml + audit-event.schema.yaml (geliefert),
`src/bridge/state_machine.py`, `src/bridge/__init__.py`,
`tests/test_state_machine.py`, `requirements.txt`, dieses Arbeitspaket,
README-Nachzug.

**NICHT enthalten:** Persistenz/Ablage der Auditspur, automatische run_id-
Vergabe aus dem Repo (→ BRIDGE-005/009), CLI-Gesamtwerkzeug (→ BRIDGE-006).

## Akzeptanzkriterien

- [x] `state-model.yaml` unverändert als einzige Übergangsquelle genutzt
- [x] `is_allowed` / `assert_transition` verhalten sich fail-closed
- [x] CLI liefert ALLOWED/DENIED mit korrekten Exit-Codes
- [x] `python -m unittest discover -s tests` ist grün
- [x] keine Übergangstabelle im Code hartkodiert
- [x] Pflicht-Footer am Ende ausgegeben

## Nächster Auftrag

**BRIDGE-005 — Ablage & Validierung** (Task/Result im Repo ablegen, gegen die
Schemas validieren, Auditspur schreiben).
