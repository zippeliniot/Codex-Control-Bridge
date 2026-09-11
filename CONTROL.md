# CONTROL.md — Arbeitsanweisung für einen ChatGPT-gesteuerten Steuerprozess

Dieses Dokument ist das Pendant zu `CLAUDE.md`, aber für einen Steuerprozess,
der **nicht** Claude Code ist, sondern ein ChatGPT-basierter Controller (z. B.
über einen GitHub-Connector, ohne lokalen Checkout). Maßgeblich bleibt
`docs/architecture/ARCHITECTURE.md`; fachliche Grundlage `docs/PROJEKTKONZEPT.md`.

`CLAUDE.md` und dieses Dokument verweisen aufeinander, damit beide Seiten die
jeweils andere Rolle kennen.

## Rollenmodell (nur Namenskonvention, keine neuen Felder)

Die Bridge kennt bereits die Felder `actor` (Audit-Event) und `created_by`
(Task/Result). Ein ChatGPT-gesteuerter Betrieb nutzt dafür feste Namen:

- `controller_actor: chatgpt-control` — der steuernde ChatGPT-Prozess
  (Pendant zu `browser-claude` auf der Claude-Seite).
- `executor_actor: codex-executor` — die ausführende Codex-Instanz
  (Pendant zu `claude-code`).

Das sind **Konventionen für bestehende Felder**, kein Schema-Zusatz. Die
maschinenlesbare Rollenzuordnung eines Projekts/Auftrags steht in
`executor` / `controller` / `review_roles` (Projektprofil bzw. Task-Override,
siehe `schemas/project.schema.yaml` und `schemas/task.schema.yaml`).

## Aktueller Betriebsmodus: nur lesend

- **Es ist derzeit kein automatischer Schreibzugriff freigegeben**, unabhängig
  davon, was ein GitHub-Connector technisch zuließe.
- Jede Schreibaktion (Branch, Commit, Push, PR, Merge, Force-Push, Deploy,
  Datenbank) setzt voraus:
  1. ein **explizit im Auftrag gelistetes** `permissions`-Recht
     (`GIT_STAGE`, `GIT_COMMIT`, `GIT_PUSH`, `PR_CREATE`, `MERGE`, `DEPLOY`,
     `DATABASE_WRITE`, `FORCE_PUSH`), und
  2. eine **vorherige ausdrückliche Freigabe durch den Menschen**.
- Ein Connector-gesteuerter Akteur bekommt pro Auftrag einen **möglichst engen**
  `permissions`-Auszug — z. B. `PR_CREATE` statt direkt `GIT_PUSH` —, niemals
  automatisch die volle Liste.
- `main`-Merge, `--force`-Push, Deploy und Datenbankänderungen nie ohne
  menschliche Freigabe (deckt sich mit `CLAUDE.md`, „Harte Regeln", Least
  privilege).

## SSOT

Ein einzelner Chatverlauf ist **niemals** alleinige Source of Truth. SSOT ist
ausschließlich das Repository (Code **und** fachliche Dokumente). Versionierbare
Zustände gehören ins Repo, nie nur in einen Chat. GitHub ist der einzige
Austauschkanal zwischen den Maschinen.

**Sofort pushen, nicht sammeln (verschärft, 12.09.2026):** Der Controller hat
per Definition keinen lokalen Checkout — er sieht nur, was auf GitHub liegt.
Jeder Executor-Commit (Codex wie Claude Code) wird unmittelbar gepusht, nicht
erst am Laufende gebündelt. Ein pausiertes Projekt muss auf GitHub trotzdem
seinen letzten echten Stand zeigen, sonst berichtet der Controller einem neuen
Steuerchat einen veralteten Zustand.

## Bootstrap-Checkliste für einen neuen ChatGPT-Steuerchat

Vor der ersten Aussage über ein Projekt lädt der Controller aus dem Repo:

1. **Projektprofil**: `projects/<project_id>/project.yaml` — Rollen
   (`executor`, `controller`, `review_roles`), `read_only`, `git_policy`,
   `allowed_machines`.
2. **Remote-Zuordnung**: `github_repo` (Slug `Besitzer/Repo`) + `default_branch`
   aus demselben Profil — das ersetzt einen lokalen Checkout für die
   GitHub-API. Ist `github_repo` `null`, ist kein Remote-Zugriff ohne lokalen
   Checkout vorgesehen → anhalten und nachfragen.
3. **Aktuelle Task-Datei**: `tasks/<BRIDGE-id>/task.yaml` (Auftragsvertrag,
   `permissions`, `acceptance_criteria`).
4. **State/Audit-Spur**: `audit/audit.jsonl` (Zustandsverlauf, `actor`).
5. **Ergebnisse/Checkpoints**: `results/<BRIDGE-id>/RUN-*/` (`result.yaml`,
   `heartbeat.json`) und die offenen Haken im zugehörigen
   `work-packages/<BRIDGE-id>.md`.
6. **Dieses Dokument** (`CONTROL.md`) selbst.

## Einstiegspunkte

- `bridge board` — welcher Auftrag wartet auf eine Kopie, inkl. Spalte
  „Führung/Prüfung" (aufgelöste `review_roles`).
- `bridge commands` — Befehlsreferenz mit aufgelöstem lokalem Pfad.

## Nummernräume

Bridge-Aufträge heißen `BRIDGE-xxx`. Fremdprojekt-Nummern (`DORF-xxx` etc.)
niemals mit Bridge-Nummern vermischen.
