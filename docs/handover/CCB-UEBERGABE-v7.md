# CCB — Übergabe an neuen Steuerchat (Stand: 11.09.2026, nach BRIDGE-023/024/025, während BRIDGE-026)

Ersetzt `docs/handover/CCB-UEBERGABE-v6.md`. **Abschnitt 0 ist bindend.**
Diese Übergabe ergänzt (ersetzt nicht) `docs/CCB-STEUERCHAT-ARBEITSWEISE.md`
und `docs/CCB-STEUERCHAT-REFERENZ.md` — beide zusätzlich lesen, siehe
Sitzungsstart-Pflichtablauf dort.

## Abschnitt 0 — Was sich seit v6 geändert hat (wichtigste Punkte zuerst)

1. **Sieben aktive Projektprofile statt nur einem.** `projects/<id>/project.yaml`
   existiert jetzt für `codex-control-bridge`, `dorfschaft`, `wetter-app`,
   `climac`, `tanken-monitor`, `bess-msrechner`, `bess-platform`. Details,
   `executor`/`controller`/`review_roles` pro Projekt: siehe Tabelle unten.
2. **`dorfschaft` ist jetzt schreibend** (`read_only: false`), bewusste
   Entscheidung des Nutzers, widerspricht **nicht** `CLAUDE.md` Regel 3 —
   diese schützt weiterhin nur Claude Code vor WSL-Übergriffen; Dorfschaft
   wird über Codex (WSL) unter ChatGPT-Kontrolle bearbeitet, nicht über
   Claude Code.
3. **`review_roles` (Führung/Prüfung) gesetzt für alle sieben Profile** —
   sichtbar im Board als „Führung/Prüfung"-Spalte.
4. **ChatGPT Codex Connector (GitHub App von `openai`) ist installiert**,
   aktuell nur für `dorfschaft` freigegeben (Repository access). Für die
   anderen sechs Repos ggf. noch zu ergänzen, falls ChatGPT dort auch lesen
   soll — bisher nicht bestätigt.
5. **`CODEX.md` und `CONTROL.md` sind jetzt Teil des Repos** (`CODEX.md` war
   in v6 nur Konzept, jetzt real gepusht) — Pendants zu `CLAUDE.md` für
   Codex-Executor bzw. ChatGPT-Controller.
6. **Sofort-Push-Pflicht verschärft (12.09.2026).** `CLAUDE.md`/`CODEX.md`/
   `CONTROL.md` verlangen jetzt: jeder Commit wird **sofort** gepusht, nicht
   erst am Laufende oder vor Maschinenwechsel gesammelt. Grund: mehrere
   Projekte laufen jetzt potenziell parallel auf HAM11/DES11, GitHub muss
   jederzeit den echten Stand zeigen.
7. **`docs/CCB-ORCHESTRATOR-KONZEPT.md` neu** — Diskussionsgrundlage für
   einen künftigen Orchestrator (Reihenfolge/Priorität über mehrere
   Projekte/Maschinen). **Kein Code, drei offene Fragen ungeklärt** (Grenze
   automatisch/Vorschlag, Form des Prioritätsfelds, Maschinen-Kapazität
   ja/nein) — nicht als `BRIDGE-0027` spezifizieren, bevor diese Fragen
   beantwortet sind.
8. **Maschinenwechsel HAM11 → DES11 erfolgt** (planmäßig laut wöchentlicher
   Rotation, `machines.md`). Steuerchat-Rolle ist maschinenunabhängig — kein
   neuer Steuerchat pro Maschine nötig, nur bei Bedarf wegen Chatlänge.
9. **Architektur-Erkenntnis (wichtig für künftige Multi-Projekt-Aufträge):**
   `project_id` wird im Auftrags-Lebenszyklus (`runner.py`/`store.py`)
   **nicht** ausgewertet — `Store`/`Runner` arbeiten immer auf einem einzigen,
   zentralen `--root` (dem CCB-Repo). `project_local_path()` ist toter Code.
   Heißt: die eigentliche Code-Arbeit an einem anderen Projekt (z. B.
   `dorfschaft`) findet **nicht** automatisch im richtigen lokalen Repo
   statt — der Executor muss selbst zwischen CCB-Store und Zielrepo
   wechseln. Details: `docs/CCB-PROJEKT-INTEGRATION.md`.

## Aktueller Stand der sieben Projektprofile

| project_id | executor | controller | review_roles.lead / support | read_only |
|---|---|---|---|---|
| codex-control-bridge | claude-code | human | anthropic / openai | false |
| dorfschaft | codex | openai | openai / anthropic | false |
| bess-msrechner | codex | openai | openai / anthropic | false |
| bess-platform | codex | openai | openai / anthropic | false |
| wetter-app | claude-code | human | anthropic / openai | false |
| climac | claude-code | human | anthropic / openai | false |
| tanken-monitor | claude-code | human | anthropic / openai | false |

## Aktueller Stand (verifiziert per frischem Klon via `bash_tool`, HEAD `d6d3d06`)

- `BRIDGE-0017` bis `BRIDGE-0025`: alle **`ARCHIVED`**.
- **`BRIDGE-0026`** (Gesamtübersicht — `bridge overview` + Web-UI-Bereich,
  alle Zustände inkl. `RUNNING`, mit Maschine): Work-Package gepusht
  (`work-packages/BRIDGE-026.md`), Claude Code hat den Lauf laut
  Web-UI-Screenshot gestartet (`status: RUNNING`, Stand kurz vor
  Chat-Ende) — **aber der Store-Eintrag selbst war zu diesem Zeitpunkt
  noch nicht auf `origin/main` sichtbar.** Erste Aktion des neuen Chats:
  frischer Klon, `task show BRIDGE-0026`/`audit show BRIDGE-0026` prüfen,
  nicht den hier genannten Stand ungeprüft übernehmen (Regel 6).
- Testsuite-Stand zuletzt verifiziert: 246 Tests grün (vor BRIDGE-0026).
- Nächste freie ID nach `BRIDGE-0026`: `BRIDGE-0027` (voraussichtlich der
  Orchestrator, aber erst nach Klärung der drei offenen Fragen in
  `CCB-ORCHESTRATOR-KONZEPT.md`).

## Nicht von selbst anfangen bei

- `BRIDGE-0027`/Orchestrator spezifizieren, bevor die drei offenen Fragen in
  `docs/CCB-ORCHESTRATOR-KONZEPT.md` vom Nutzer beantwortet sind.
- GitHub-App-Repository-Freigabe für die restlichen sechs Repos (nur
  `dorfschaft` bisher bestätigt) — nicht ungefragt erweitern.
- `review_roles`/`executor`/`controller` weiterer Projekte ändern, ohne
  erneute ausdrückliche Angabe wie in dieser Sitzung.

## Offene nächste Schritte (Reihenfolge)

1. `BRIDGE-0026` verifizieren (frischer Klon, Tests, Diff gegen
   Akzeptanzkriterien) sobald `run finish` gemeldet wird — **nicht** den
   Pflicht-Footer allein glauben, wie bei jedem Auftrag zuvor auch.
2. Über Web-UI oder CLI abschließen (`Kopiert → Review`, `Archivieren`).
3. Erst danach: Orchestrator-Fragen mit dem Nutzer klären, dann ggf.
   `BRIDGE-0027` spezifizieren.
