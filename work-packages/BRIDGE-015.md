# BRIDGE-015 — ID-Format erweitern: beliebiger Projekt-Präfix + 4-stellige Nummer

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-015 |
| project_id | codex-control-bridge |
| task_class | FEATURE |
| depends_on | BRIDGE-004, BRIDGE-005, BRIDGE-010 |
| permission | WORKTREE_WRITE, TEST_EXECUTION (nur innerhalb des Repos) |
| executor | claude-code |

## Kontext

Voraussetzung für das kommende Terminal-Board (BRIDGE-016), das projekt-
übergreifend BRIDGE- **und** DORF-Aufträge (und künftige weitere Projekte)
anzeigen soll. Beim Review wurde festgestellt: das aktuelle Schema lässt
**ausschließlich** `BRIDGE-xxx`-IDs zu (`^BRIDGE-[0-9]{3,}$`), obwohl
"Getrennte Nummernräume" schon seit BRIDGE-001 als Guardrail gilt — ein
`DORF-015`-Auftrag könnte im Store bisher gar nicht angelegt werden.

**Entschiedenes neues Format** (verbindlich für alle Projekte, jetzige wie
künftige): `<PRÄFIX>-<NNNN>` — Präfix max. 8 Großbuchstaben, danach ein `-`,
danach genau 4 Ziffern. Beispiele: `BRIDGE-0015`, `DORF-0042`, `ENFAN-0001`.

Betrifft **nur** die `bridge_task_id` (System-ID für Aufträge/Ergebnisse/
Heartbeats/Audit-Einträge) und den `task_prefix` im Projektprofil. **NICHT**
betroffen: die Nummerierung der `work-packages/BRIDGE-xxx.md`-Dateien selbst
(z. B. dieses Dokument) — das ist eine reine Dokumentnamenskonvention, nicht
schemavalidiert, bleibt 3-stellig wie bisher.

## Bereits von der Steuerebene geliefert (NICHT verändern)

Fünf Schema-Dateien, minimal geändert (nur die Muster, sonst nichts):

- `schemas/task.schema.yaml` — `bridge_task_id` und `depends_on`-Items:
  `^[A-Z]{1,8}-[0-9]{4}$`
- `schemas/audit-event.schema.yaml` — `bridge_task_id`: gleiches Muster
- `schemas/result.schema.yaml` — `bridge_task_id`: gleiches Muster
- `schemas/heartbeat.schema.yaml` — `bridge_task_id`: gleiches Muster
- `schemas/project.schema.yaml` — `task_prefix`: `^[A-Z]{1,8}$` (max. 8
  Großbuchstaben, passend zum neuen `bridge_task_id`-Format)

Bereits geprüft: bestehende Profile (`codex-control-bridge`,
`projects/examples/dorfschaft.project.yaml`) validieren weiterhin.
Testsuite mit den neuen Schemas laufen lassen zeigt den erwarteten Umfang:
**118 Tests, davon 72 rot** (harte 3-stellige Test-IDs wie `BRIDGE-900`
passen nicht mehr) — das ist erwartet und der Kern dieses Auftrags.

## Von Claude Code umzusetzen

### 1) Zwei Python-Konstanten nachziehen (identisches Muster wie in den Schemas)

- `src/bridge/store.py`, `_ID_RE`: `re.compile(r"^[A-Z]{1,8}-[0-9]{4}$")`
- `src/bridge/heartbeat.py`, `_ID_RE`: dasselbe

(`_RUN_RE` in beiden Dateien bleibt unverändert — betrifft nur `RUN-xx`.)

### 2) Testsuite auf das neue Format bringen

Alle **echten Task-ID-Werte** (Feld `bridge_task_id`, `depends_on`,
CLI-Argument `task_id`, Pfadsegmente wie `tasks/BRIDGE-900/`) in `tests/`
von 3-stelligen auf 4-stellige Nummern umstellen — reines Zero-Padding,
keine Umbenennung: `BRIDGE-900` → `BRIDGE-0900`, `BRIDGE-404` → `BRIDGE-0404`,
usw. Betrifft laut Suche u. a. `BRIDGE-900` bis `BRIDGE-9xx`-Bereiche in
`test_store.py`, `test_runner.py`, `test_cli.py`, `test_importer.py`,
`test_adapter.py`, `test_integration_readonly.py` und ggf. weitere.

**Wichtige Abgrenzung:** Verweise auf **Arbeitspaket-Nummern** in Kommentaren,
Docstrings oder Audit-`reason`-Strings (z. B. `"BRIDGE-013"`/`"BRIDGE-014"`
als Bezeichner einer Spezifikation, nicht als Auftrags-ID-Feldwert) **nicht**
anfassen — das sind Dokumentverweise, kein Datenfeld. Im Zweifel: nur ändern,
was tatsächlich als `bridge_task_id`/ID-artiger Wert in eine Task-, Result-,
Heartbeat- oder Audit-Struktur eingesetzt wird.

Ein neuer Test ergänzen, der das neue Format direkt prüft (unabhängig von
Fixtures): ein Task mit `DORF-0001` (Präfix ≠ BRIDGE) lässt sich anlegen und
validieren; ein 3-stelliges `BRIDGE-042` wird abgelehnt; ein 9-Buchstaben-
Präfix wird abgelehnt.

### 3) README.md nachziehen (kleine Doku-Konsistenz)

- Zeile mit "Auftragsnummerierung: `BRIDGE-001`, `BRIDGE-002`, …" auf das neue
  Format umstellen (`BRIDGE-0001`, `BRIDGE-0002`, … — Präfix max. 8
  Großbuchstaben + 4 Ziffern, projektübergreifend z. B. auch `DORF-0001`).
- Die paar Beispielbefehle mit `BRIDGE-042` auf `BRIDGE-0042` anpassen.

### 4) Abschluss

- `python -m unittest discover -s tests` grün (118 bisherige, angepasst,
  + mind. 1 neuer Test für das neue Format).
- `work-packages/BRIDGE-015.md`: Akzeptanzkriterien `[ ]` → `[x]` abhaken.
- Pflicht-Footer: `Auftrag: BRIDGE-015 / Lauf: RUN-01 / Status: ...`

## Scope

**Enthalten:** neues ID-Format in allen 5 Schemas (geliefert) + 2
Python-Konstanten, komplette Testsuite auf 4-stellig umgestellt, README-
Nachzug, neuer Format-Test.

**NICHT enthalten:**
- das Terminal-Board selbst → BRIDGE-016 (bisherige Nummer BRIDGE-015 im
  ursprünglichen Plan verschiebt sich um eins).
- Cross-Check, dass ein Task-Präfix tatsächlich zu einem registrierten
  Projektprofil gehört (nur Format wird geprüft, nicht Registrierung) —
  bewusst zurückgestellt, da BRIDGE-016 ohnehin eine Projekt-Registry
  einführt und diesen Check dort sinnvoll mit erledigen kann.
- Umbenennung der `work-packages/BRIDGE-xxx.md`-Dateien (bleibt 3-stellige
  Dokumentnamenskonvention, s. o.).

## Akzeptanzkriterien

- [ ] alle 5 Schema-Muster auf `^[A-Z]{1,8}-[0-9]{4}$` bzw. `^[A-Z]{1,8}$`
      (geliefert, hier nur bestätigen)
- [ ] `store.py`/`heartbeat.py` `_ID_RE` nachgezogen
- [ ] `DORF-0001` (o. ä. Nicht-BRIDGE-Präfix) lässt sich anlegen/validieren
- [ ] 3-stelliges Alt-Format wird abgelehnt (Regressionstest vorhanden)
- [ ] gesamte Testsuite grün (alte Fixtures umgestellt + neuer Test)
- [ ] README.md konsistent mit neuem Format
- [ ] Pflicht-Footer am Ende

## Nächster Auftrag

**BRIDGE-016 — Projekt-Registry + Copy-Paste-Board (Terminal).** Zeigt
projektübergreifend alle Aufträge in den zwei BRIDGE-014-Wartezuständen
(jetzt mit echten Multi-Projekt-IDs möglich), sortiert nach Auftragsnummer +
`depends_on`, plus eine Befehlsreferenz für die gängigsten Kommandos
(u. a. `scripts/handover-check.ps1`/`.sh`, die bereits existieren).
