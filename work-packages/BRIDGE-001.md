# BRIDGE-001 — Bestandsfreie Projektinitialisierung und verbindliche Architekturgrundlage

| Feld | Wert |
|------|------|
| bridge_task_id | BRIDGE-001 |
| project_id | codex-control-bridge |
| task_class | INIT / ARCHITECTURE |
| permission | READ_ONLY + WORKTREE_WRITE (nur Neuanlage von Struktur/Doku) |
| git_policy | GIT_STAGE/GIT_COMMIT/GIT_PUSH durch Benutzer; keine kritischen Aktionen |
| status | COMPLETED (Ergebnisvertrag erfüllt) |

## Auftrag

Ein neues, von Dorfschaft unabhängiges Projekt „Codex Control Bridge" auf
Grundlage des Projektkonzepts bestandsfrei initialisieren und die verbindliche
Architekturgrundlage anlegen. Beginn mit Architektur und Stufe 1.

## Scope

**Enthalten:**
- Repository-Grundstruktur nach Konzept-Abschnitt 18
- README (Projektüberblick, Kernprinzipien, Struktur, Entwicklungsstand)
- Verbindliche Architekturgrundlage (`docs/architecture/ARCHITECTURE.md`)
- Verzeichnisdoku (`docs/architecture/directory-structure.md`)
- Maschinen- und Umgebungsregister (`docs/architecture/machines.md`)
- Verbindliches Sicherheitsmodell (`docs/security/SECURITY-MODEL.md`)
- Verbindliche Handover-Regeln inkl. wöchentlicher Rotation
  (`docs/handover/HANDOVER.md`)
- Fachliches Konzept im Repo (`docs/PROJEKTKONZEPT.md`)
- Guardrails für Claude Code (`CLAUDE.md`, `.claude/settings.json`) — native
  Windows-Ausführung, Sperre von `\\wsl.localhost`, WSL-/System-Schutz
- Übergabe-Gate fail-closed: `scripts/handover-check.ps1` (Windows/PowerShell)
  und `scripts/handover-check.sh` (Git Bash)
- Zeilenenden-Normalisierung (`.gitattributes`)
- Platzhalter/Wegweiser in `docs/concepts`, `docs/protocols`, `schemas`,
  `projects/examples`, `src`

**Bewusst NICHT enthalten (spätere Arbeitspakete):**
- Schema-Inhalte → BRIDGE-002 (Task), BRIDGE-003 (Result), BRIDGE-010 (Project)
- Zustands-/Resume-Implementierung → BRIDGE-004 / BRIDGE-009
- Ablage/Validierung → BRIDGE-005
- CLI → BRIDGE-006
- Result-Importer → BRIDGE-007
- Watcher → BRIDGE-008
- Projektprofil-Mechanismus → BRIDGE-010
- Dorfschaft-Adapter (nur konzeptionell, read-only) → BRIDGE-011
- Dorfschaft Read-only-Integrationstest → BRIDGE-012

## Ergebnisvertrag (result contract)

Angelegte Artefakte:

```
README.md
docs/architecture/ARCHITECTURE.md
docs/architecture/directory-structure.md
docs/security/SECURITY-MODEL.md
docs/handover/HANDOVER.md
docs/concepts/README.md
docs/protocols/README.md
schemas/README.md
projects/examples/README.md
src/README.md
src/{bridge,runner,watcher,storage,adapters}/.gitkeep
tests/.gitkeep
scripts/.gitkeep
work-packages/BRIDGE-001.md
.gitignore
```

## Erfüllte Akzeptanzkriterien (Stufe 1, Teilmenge aus Konzept-Abschnitt 29)

- [x] Repository und Grundstruktur aufgebaut
- [x] Projekt bestandsfrei initialisiert (nur vorheriger README-Stub ersetzt)
- [x] Verbindliche Architekturgrundlage vorhanden
- [x] Getrennte Nummernräume dokumentiert (BRIDGE-* vs. externe IDs)
- [x] Dorfschaft nicht verändert
- [x] Keine produktive Integration
- [x] Handover-Prinzip (SSOT im Repository) festgeschrieben
- [x] Maschinenregister HAM11/HAM01 + DES11/DES01 dokumentiert (DES11 zu bestätigen)
- [x] Wöchentliche Rotation (Do/Fr/Mo) festgeschrieben
- [x] Ubuntu-Schutzbereich für Claude Code festgeschrieben
- [x] Übergabe-Gate als ausführbares Skript vorhanden (PowerShell + Bash)
- [x] Fachliche Dokumente (Konzept) im Repo
- [x] Isolationsstrategie entschieden: Claude Code als native Windows-App,
      Codex/Dorfschaft-Ubuntu strukturell getrennt
- [x] Zugriff auf WSL-Distros (`\\wsl.localhost`) per Deny-Regel gesperrt
- [x] E: als namensgleich-aber-physisch-getrennt dokumentiert

## Nächster Auftrag

**BRIDGE-002 — Task-Schema definieren** (Konzept-Abschnitt 5).
