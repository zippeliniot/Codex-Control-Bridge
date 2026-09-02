# CLAUDE.md — Arbeitsanweisung für Claude Code

Dieses Repository ist die **Codex Control Bridge (CCB)**, eine
projektunabhängige Vermittlungsschicht für Aufträge/Ergebnisse zwischen einem
Steuerprozess und einer Ausführungsinstanz. Maßgeblich ist
`docs/architecture/ARCHITECTURE.md`. Fachliche Grundlage: `docs/PROJEKTKONZEPT.md`.

## Ausführungsmodell

- Claude Code läuft als **native Windows-App** und arbeitet ausschließlich in
  `E:\_DEV\Codex-Control-Bridge`.
- Claude im Browser ist die Steuer-/Review-Ebene. GitHub ist der einzige
  Austauschkanal zwischen den Maschinen und die SSOT.

## Harte Regeln (nicht verhandelbar)

1. **Ubuntu/WSL nicht verändern.** Das Ubuntu/WSL wird von Codex für das
   Dorfschaft-Projekt genutzt. Keine WSL-Änderungen, keine Systempakete, kein
   `sudo`, keine globale Konfiguration.
2. **Nicht in die WSL-Distros hineingreifen.** Keine Zugriffe über
   `\\wsl.localhost\...`, `\\wsl$\...` oder `wsl`-Aufrufe.
3. **Dorfschaft nicht anfassen.** Weder lesen noch schreiben, außer in
   ausdrücklich als Read-only deklarierten Aufträgen (BRIDGE-011/012).
4. **Nur innerhalb des Repos arbeiten.** Keine Schreibzugriffe außerhalb
   `E:\_DEV\Codex-Control-Bridge`.
5. **Fail-closed.** Bei jeder Unsicherheit (falscher Branch, unerwarteter HEAD,
   nötige System-/WSL-Änderung, unklare Maschinenidentität) → anhalten und
   nachfragen, nicht improvisieren.
6. **Least privilege.** Default ist lesend. Kritische Aktionen — Merge nach
   `main`, `--force`-Push, Deploy, Datenbankänderungen — nie ohne ausdrückliche
   menschliche Freigabe.
7. **Getrennte Nummernräume.** Bridge-Aufträge heißen `BRIDGE-xxx`, niemals
   `DORF-xxx` verwenden oder vermischen.

## Maschinen & Wechsel

Zwei **physisch getrennte** Systeme (Register in `docs/architecture/machines.md`):

- `HAM11` (physisch) / `HAM01` (logische Umgebung)
- `DES11` (physisch) / `DES01` (logische Umgebung)

Das Laufwerk `E:` ist auf beiden nur namensgleich, nicht geteilt.

**GitHub ist der einzige Übergabekanal.** Rotation: Donnerstag Upload von HAM →
GitHub, Freitag Übernahme durch DES, Montag Rückgabe DES → GitHub → HAM. **Vor
jedem Wechsel muss alles auf GitHub liegen — Code und fachliche Dokumente.**

Vor jeder Übergabe ausführen: `scripts\handover-check.ps1` (bzw. unter Git Bash
`bash scripts/handover-check.sh`). Meldet das Skript `FAIL`, ist die Übergabe
nicht zulässig, bis alles committed und gepusht ist.

## Modellsteuerung

Das schwächste zuverlässig geeignete Modell mit der niedrigsten ausreichenden
Denkstufe verwenden. Qualität, Sicherheit, Datenintegrität und korrekte
Git-/Teststeuerung haben Vorrang vor Tokenersparnis.

## Arbeitsweise

- Jedes Arbeitspaket wird in `work-packages/BRIDGE-xxx.md` dokumentiert (Auftrag,
  Scope, Ergebnisvertrag, Akzeptanzkriterien).
- `COMPLETED` heißt „Ergebnisvertrag erfüllt", nicht „fachlich freigegeben".
- Versionierbare Zustände gehören ins Repo, nie nur lokal oder in einen Chat.
