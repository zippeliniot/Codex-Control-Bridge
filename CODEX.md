# CODEX.md — Arbeitsanweisung für einen Codex-Executor unter der Bridge

Pendant zu `CLAUDE.md`, aber für **Codex als ausführende Instanz** unter
einem ChatGPT-gesteuerten Controller (siehe `CONTROL.md`, das Pendant
zur Steuerseite). **Wichtiger Unterschied zu `CLAUDE.md`:** Dieses
Dokument ist **projektunabhängig** — `CLAUDE.md` ist fest auf das
CCB-Repo selbst zugeschnitten (dort ist `executor: claude-code`, siehe
`projects/codex-control-bridge/project.yaml`). Codex ist in diesem Repo
**kein** Executor; `CODEX.md` gilt für **jedes andere Projekt**, dessen
Profil (`projects/<project_id>/project.yaml`) `executor: codex` setzt.

Maßgeblich bleibt in jedem Fall `docs/architecture/ARCHITECTURE.md`;
fachliche Grundlage `docs/PROJEKTKONZEPT.md`. `CONTROL.md` und dieses
Dokument verweisen aufeinander, damit Steuer- und Ausführungsseite
dieselbe Rollenaufteilung kennen.

## Ausführungsmodell

- Codex läuft in der **Ubuntu/WSL-Umgebung** der jeweiligen physischen
  Maschine (`HAM11`/`DES11`, siehe `docs/architecture/machines.md`) —
  nicht nativ unter Windows wie Claude Code.
- Laut Konzept-Abschnitt 12 (`PROJEKTKONZEPT.md`) unterscheidet die
  Bridge `runtime: WSL` von `runtime: WINDOWS_NATIVE` als Teil der
  Maschinenidentität — ein Auftrag kann das gezielt verlangen.
- **Offen, vor dem ersten echten Einsatz zu klären, nicht anzunehmen:**
  Der genaue Zugriffspfad von der WSL-Seite auf das jeweilige
  Projekt-Repository (Standardkonvention wäre ein Mount wie
  `/mnt/e/...`, aber das ist in diesem Repo **nicht** dokumentiert
  bestätigt) — vor dem ersten Auftrag mit `executor: codex` explizit
  festlegen und hier ergänzen, nicht raten.
- Akteur-Namenskonvention laut `CONTROL.md`: `executor_actor:
  codex-executor` (Pendant zu `claude-code`), `controller_actor:
  chatgpt-control` (Pendant zu `browser-claude`) — feste Namen für die
  bestehenden Felder `actor`/`created_by`, kein Schema-Zusatz.

## Harte Regeln (nicht verhandelbar)

1. **Nur innerhalb des im Auftrag benannten Projekt-Repos arbeiten.**
   Welches Repo das ist, ergibt sich aus `project_id` im Auftrag →
   `projects/<project_id>/project.yaml` → Feld `repository`. Niemals in
   ein anderes Projekt hineingreifen, auch nicht in die Bridge selbst
   (`Codex-Control-Bridge`), außer ein Auftrag ist **ausdrücklich**
   dafür angelegt.
2. **`read_only: true` im Projektprofil ist bindend und wird technisch
   erzwungen** (`src/bridge/adapter.py`, `ReadOnlyAdapter`) — bei
   `read_only: true` sind ausschließlich Git-Lesebefehle aus
   `schemas/git-readonly-allowlist.yaml` erlaubt, alles andere wird
   fail-closed abgelehnt. Codex darf diese Grenze nicht umgehen, auch
   nicht über Umwege (z. B. Shell-Befehle statt Git-Kommandos).
3. **Nur die im Auftrag (`task.yaml` → `permissions`) explizit
   gelisteten Rechte nutzen**, nie mehr annehmen. Mögliche Werte:
   `READ_ONLY`, `WORKTREE_WRITE`, `TEST_EXECUTION`, `GIT_STAGE`,
   `GIT_COMMIT`, `GIT_PUSH`, `PR_CREATE`, `MERGE`, `DEPLOY`,
   `DATABASE_WRITE`, `FORCE_PUSH`. Laut `CONTROL.md` aktueller
   Betriebsmodus: **kein automatischer Schreibzugriff freigegeben** —
   jede Schreibaktion braucht zusätzlich zur Auftragsberechtigung eine
   vorherige ausdrückliche menschliche Freigabe.
4. **`--force`-Push ist immer verboten**, unabhängig von `permissions`
   — projektübergreifende Konvention dieses gesamten Systems, keine
   Ausnahme.
5. **Fail-closed.** Bei jeder Unsicherheit (falscher Branch,
   unerwarteter HEAD, unklare Maschinenidentität, unklarer
   WSL-Zugriffspfad, fehlende `permissions` für eine benötigte Aktion)
   → anhalten und über den Controller (ChatGPT) an den Menschen
   zurückmelden, nicht improvisieren.
6. **Least privilege.** Default ist lesend. Kritische Aktionen — Merge
   nach dem Standard-Branch, `--force`-Push, Deploy,
   Datenbankänderungen — nie ohne ausdrückliche menschliche Freigabe,
   auch wenn `permissions` sie technisch auflisten würde.
7. **Getrennte Nummernräume.** Aufträge nutzen den `task_prefix` des
   jeweiligen Projekts (`projects/<id>/project.yaml`) — niemals
   `BRIDGE-xxx` für ein fremdes Projekt verwenden oder Nummernräume
   vermischen.

## Checkpoint & Resume, Heartbeat (verbindlich)

Gleiche Konvention wie bei Claude Code (`CLAUDE.md`): in kleinen,
nachvollziehbaren Schritten arbeiten statt einem einzigen großen
Endcommit, regelmäßig Heartbeat schreiben (`bridge watch heartbeat`
bzw. `run beat`), damit ein unterbrochener Lauf über
`INTERRUPTED`→`WAITING_FOR_RESUME`→`run resume` sauber wieder
aufgenommen werden kann, statt undefiniert hängen zu bleiben.

## Auftragsabschluss — Pflicht-Footer

Wie bei Claude Code: jeder abgeschlossene Lauf endet mit
`run finish --status <STATUS> --actor codex-executor --summary "..."`
und dem Klartext-Footer
`Auftrag: <ID> / Lauf: <RUN-ID> / Status: <STATUS>` an den Controller
zurückgemeldet. Ist `--commit` aus dem Projektprofil heraus sinnvoll
(analog BRIDGE-025-Mechanik, `gitops.py`), gilt dieselbe
Whitelist-/Branch-Logik wie für Claude Code — kein `git add -A`, kein
`--force`.

## Sofort pushen, nicht sammeln (verschärft, 12.09.2026)

Wie bei Claude Code (`CLAUDE.md` „Checkpoint & Resume" Punkt 4): jeder
Commit wird **unmittelbar gepusht**, nicht erst am Laufende gebündelt.
Bei mehreren parallel laufenden Projekten/Maschinen ist GitHub die
einzige Stelle, an der ein neuer Steuerchat oder eine andere Maschine
den echten Stand sieht. Ein pausiertes Projekt muss auf GitHub trotzdem
seinen letzten echten Stand zeigen, nicht einen veralteten.

## Status dieses Dokuments

**Noch nicht in der Praxis erprobt** — bisher gibt es kein aktives
Projektprofil mit `executor: codex` (das Dorfschaft-Beispiel unter
`projects/examples/` ist eine Vorlage, kein aktives Profil). Vor dem
ersten echten Einsatz: WSL-Zugriffspfad klären (siehe oben), und diesen
Status-Absatz durch die erste reale Erfahrung ersetzen.
