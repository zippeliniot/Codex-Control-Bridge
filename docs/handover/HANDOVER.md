# Handover — Rechnerunabhängige Übergabefähigkeit

> **Status:** verbindlich ab BRIDGE-001.

Das Bridge-Projekt muss vollständig **rechnerunabhängig übergabefähig** sein.
Ein Wechsel zwischen Rechnern darf keine versteckte lokale Abhängigkeit erzeugen.

## Leitregel (SSOT)

> Auftrag, Zustand, Ergebnis **und fachliche Dokumente** müssen **außerhalb des
> Chatverlaufs** reproduzierbar auffindbar sein — konkret: im GitHub-Repository.

## GitHub ist der einzige Übergabekanal

Der Austausch zwischen den Maschinen läuft ausschließlich über GitHub. Nicht
akzeptabel als alleinige Quelle: Chatverlauf, lokale temporäre Datei, Clipboard,
ChatGPT-/Claude-Memory, Codex-Historie oder ein nur auf einem Rechner
vorhandener Zustand.

## Wöchentliche Rotation

Vollständiges Maschinenregister: [`../architecture/machines.md`](../architecture/machines.md).

| Tag | Aktion | Richtung |
|-----|--------|----------|
| **Donnerstag** | 100 % auf GitHub hochladen | `HAM11`/`HAM01` → GitHub |
| **Freitag** | Weiterbearbeitung | GitHub → `DES11`/`DES01` |
| **Montag** | Rückgabe (vorher 100 % Upload) | `DES11`/`DES01` → GitHub → `HAM11`/`HAM01` |

**Kein Wechsel ohne vollständigen, gepushten Stand.**

## Übergabe-Gate (vor JEDEM Wechsel)

Ausführen (native Windows): `scripts\handover-check.ps1`
Alternativ unter Git Bash: `bash scripts/handover-check.sh`

Die Übergabe ist nur zulässig, wenn alle Punkte erfüllt sind (sonst
fail-closed):

- [ ] alle Änderungen committed (kein „dirty" Working Tree)
- [ ] keine untracked Dateien, die verloren gehen würden
- [ ] keine offenen Stashes
- [ ] aktueller Branch = Übergabebranch (Standard: `main`)
- [ ] lokal **nicht ahead** von `origin` (alles gepusht)
- [ ] Pflichtdokumente vorhanden (Konzept + Architekturgrundlage)

## Was zwingend im Repo liegen muss

Nicht nur Code, sondern auch die **fachliche Arbeitsgrundlage**, damit die
übernehmende Maschine sofort arbeiten kann:

- `docs/PROJEKTKONZEPT.md` (fachliches Konzept)
- `docs/architecture/` (Architekturgrundlage, Struktur, Maschinenregister)
- `docs/security/`, `docs/handover/`
- alle `work-packages/BRIDGE-*.md`
- ab BRIDGE-002/003: `schemas/`
