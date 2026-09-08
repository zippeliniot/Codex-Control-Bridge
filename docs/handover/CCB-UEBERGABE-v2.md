# Codex Control Bridge (CCB) — Übergabe an neuen Chat (Stand nach BRIDGE-018)

Dieses Dokument fasst Projekt, Stand und offene nächste Schritte zusammen,
damit ein neuer Chat nahtlos weiterarbeiten kann. Löst die vorherige
Übergabe (CCB-UEBERGABE.md, Stand nach BRIDGE-013) ab.

---

## 1. Was das Projekt ist

Die **Codex Control Bridge (CCB)** ist eine projektunabhängige Vermittlungsschicht
für strukturierte Aufträge/Ergebnisse zwischen einem **Steuerprozess** (Claude
im Browser) und einer **Ausführungsinstanz** (Claude Code). GitHub ist die
**einzige Quelle (SSOT)**.

- Repo (öffentlich): https://github.com/zippeliniot/Codex-Control-Bridge
- Fachliches Konzept: `docs/PROJEKTKONZEPT.md`

**Kernziel, seit BRIDGE-014 real erreicht:** ein Copy-Paste-Dirigent — die
Bridge zeigt projektübergreifend, welcher Auftrag als Nächstes kopiert werden
muss und in welcher Reihenfolge (`bridge board`), plus eine Befehlsreferenz
(`bridge commands`) und ein dauerhaftes Überwachungsfenster
(`bridge board --watch`).

## 2. Rollenverteilung (unverändert)

- **Claude im Browser (Steuer-/Review-Ebene):** schreibt Spezifikationen als
  `work-packages/BRIDGE-xxxx.md` **+ seit BRIDGE-017 zusätzlich ein echtes
  `tasks/incoming/BRIDGE-xxxx.yaml`** (Staging-Pfad, s. Abschnitt 6!),
  reviewt den gepushten Stand gegen GitHub (frischer Klon, Tests, teils
  gezielte End-to-End-Funktionstests). Kann NICHT pushen.
- **Claude Code (Ausführung, native Windows-App):** implementiert Code +
  Tests, führt seit BRIDGE-017 auch die Bridge-CLI-Befehle selbst aus
  (`task create`, `run start`, `run finish`), committet klein, pusht (nach
  ask-Bestätigung).
- **Mensch:** spielt Spezifikations-ZIPs ein, bestätigt Claude-Code-Aktionen,
  pusht, führt `task copied`/`task archive` für den finalen Abschluss aus,
  stößt den jeweils anderen Chat an.

**Ablauf pro Paket (aktuelle Fassung):**
1. Browser-Claude schreibt Spezifikation (`work-packages/BRIDGE-xxxx.md`)
   + `tasks/incoming/BRIDGE-xxxx.yaml` → ZIP.
2. Mensch: `git pull` (!), ZIP einspielen, committen, pushen.
3. Claude Code: `bridge task create tasks/incoming/BRIDGE-xxxx.yaml` (Staging-
   Datei danach löschen), `bridge run start`, implementiert, testet,
   `bridge run finish --status COMPLETED`, committet (nicht pushen).
4. Mensch pusht nach Bestätigung durch Browser-Claude.
5. Browser-Claude reviewt gegen GitHub (frischer Klon, Tests, Funktionstest).
6. Nach Freigabe: Mensch führt `task copied` + `task archive` lokal aus,
   committet/pusht den finalen Zustand.

## 3. Systemlandschaft (unverändert)

- Zwei physisch getrennte Windows-PCs: **HAM11** und **DES11**, Basis auf
  beiden `E:\_DEV` (in `registry.yaml` versioniert, s. Abschnitt 5).
  Lokaler Pfad: `E:\_DEV\Codex-Control-Bridge`.
- Claude Code läuft nativ unter Windows, nicht in WSL.
- Wöchentliche Rotation, `scripts/handover-check.ps1`/`.sh` muss PASS zeigen.
- **Wichtige gelernte Lektion:** Vor JEDEM Maschinenwechsel und vor jedem
  neuen ZIP zuerst `git pull origin main` — ein veralteter lokaler Klon
  (zuletzt: acht Pakete Rückstand auf HAM11) führt sonst zu vermeidbaren
  Push-Konflikten.
- Python-Arbeit immer im repo-lokalen `.venv`
  (`.venv\Scripts\python.exe ...`, NICHT nacktes `python`, sonst fehlt `yaml`).
- Aktuell wird auf **HAM11** gearbeitet.

## 4. Verbindliche Regeln (Guardrails, unverändert + ergänzt)

- SSOT im Repo; Fail-closed bei jeder Unsicherheit.
- Least privilege: Bridge/Watcher/Runner führen NIE Git-Aktionen aus.
- Getrennte Nummernräume nach Projekt-Präfix — **seit BRIDGE-015 erweitert:**
  `bridge_task_id`-Format ist jetzt `<PRÄFIX max. 8 Großbuchstaben>-<4 Ziffern>`
  (z. B. `BRIDGE-0018`, `DORF-0042`), nicht mehr nur `BRIDGE-xxx` mit 3
  Ziffern. `work-packages/*.md`-Dateinamen bleiben davon unberührt (weiterhin
  3-stellig, reine Dokumentkonvention).
- `read_only: true` hart erzwungen (Allowlist).
- Python-Arbeit immer im repo-lokalen `.venv`.
- Pflicht-Footer am Ende jedes Claude-Code-Auftrags:
  `Auftrag: BRIDGE-xxxx / Lauf: RUN-yy / Status: ...`
- Checkpoint-&-Resume: kleine Commits.
- Claude-Code-Auto-Modus AUS halten; vor jedem Auftrag Modell UND Denkstufe
  angeben.
- Beim Anleiten: vor jedem Befehl angeben, WO er läuft, Befehle als
  kopierbare Codeblöcke.
- **Neu:** `/clear` in Claude Code nach jedem abgeschlossenen, gepushten
  Paket, bevor das nächste beginnt (Aufträge sind bewusst in sich
  geschlossen, SSOT ist das Repo, nicht der Chatverlauf).
- **Neu:** Task-Spezifikationen für `task create` immer über
  `tasks/incoming/BRIDGE-xxxx.yaml` liefern, NIE direkt am kanonischen
  Store-Pfad `tasks/BRIDGE-xxxx/task.yaml` — sonst schlägt `task create`
  fail-closed fehl ("Auftrag existiert bereits"), da Quell- und Zielpfad
  identisch wären.

## 5. Stand: fertig, reviewt, auf GitHub (BRIDGE-001 bis BRIDGE-018)

**BRIDGE-001 bis BRIDGE-013:** wie in der Vorgänger-Übergabe beschrieben,
unverändert gültig (Kernmodule, Schemas, Zustandsmodell, Store, CLI, Watcher,
Runner, Profile, Dorfschaft-Adapter, Read-only-Integrationstest,
executor/controller-Profilfelder).

**BRIDGE-014 — Übergabe-Wartezustände + Auto-Chain:**
zwei neue Zustände `WAITING_FOR_HANDOFF_TO_EXECUTOR` (Steuerung→Executor) und
`WAITING_FOR_COPY_TO_CONTROL` (Executor→Steuerung). `task create` landet
automatisch im ersten, `run finish --status COMPLETED` automatisch im
zweiten. Komfortbefehl `task copied` (→ REVIEW_REQUIRED), fail-closed exakt
aus `WAITING_FOR_COPY_TO_CONTROL` heraus (Nachbesserung in RUN-02 — der
erste Versuch war zu großzügig, siehe `work-packages/BRIDGE-014.md`
"Nachbesserung RUN-02").

**BRIDGE-015 — ID-Format erweitert:**
`bridge_task_id`/`depends_on`/`task_prefix` auf `<PRÄFIX bis 8 Großbuchst.>-
<4 Ziffern>` umgestellt (vorher nur `BRIDGE-xxx`, 3-stellig). Voraussetzung
für projektübergreifende Aufträge (`DORF-0001` etc.). Ca. 171 Testfixtures
mechanisch angepasst.

**BRIDGE-016 — Copy-Paste-Board + Registry:**
`registry.yaml`/`registry.schema.yaml` (COMPUTERNAME → lokale Basis, NUR für
Befehlsreferenz, nicht für Auftragssuche — alle Aufträge liegen in einem
zentralen Store). `bridge board` zeigt projektübergreifend beide
BRIDGE-014-Wartezustände, sortiert, mit `depends_on`-Hinweis, fail-soft bei
fehlendem Profil. `bridge commands` zeigt Befehlsreferenz (u. a.
`handover-check`), fail-closed bei unbekannter Maschine ohne
`CCB_PROJECT_BASE`-Override.

**BRIDGE-017 — Komfortbefehl `task archive`:**
setzt einen Auftrag nach `ARCHIVED`, kein Sonderfall-Check (bestehende
Zustandstabelle reicht). **Erstes Paket, das komplett über die Bridge selbst
lief** (nicht nur als Doku) — von `task create` bis `ARCHIVED` durchgespielt
und verifiziert.

**BRIDGE-018 — `bridge board --watch`:**
Board-Rendering in Daten-/Text-Teil getrennt, `--watch`/`--interval`
(Default 15s) nach dem Muster von `watcher.loop()`, kein Bildschirm-Löschen
(stattdessen Zeitstempel-Trennzeilen), `Strg+C` sauber abgefangen (mit
echtem SIGINT verifiziert, nicht nur im Unittest gemockt).
`scripts/board-watch.bat` liegt im Repo — Doppelklick-Starter fürs
Überwachungsfenster, funktioniert unabhängig vom eigenen Speicherort,
richtet `.venv` beim ersten Lauf selbst ein.

**Testsuite:** 151 Tests, grün bei frischem Klon (mehrfach verifiziert).

**Prüfen im neuen Chat:** letzten Commit-Stand von `origin/main` gegenlesen
(sollte bei `57095f9` oder später stehen), `bridge board` sollte leer sein
(beide Aufträge BRIDGE-0017/0018 sind `ARCHIVED`).

## 6. Wichtige technische Klarstellungen für den neuen Chat

- **Ein zentraler Store, keine Multi-Repo-Traversierung:** Alle Aufträge
  (BRIDGE-xxxx und künftig DORF-xxxx) liegen in diesem einen Repo
  (`tasks/`, `results/`, `audit/`). Die Registry wird nur für lokale Pfade
  in der Befehlsreferenz gebraucht, nicht um Aufträge zu finden.
- **`tasks/incoming/` ist reines Staging**, kein dauerhafter Ablageort —
  Dateien dort nach erfolgreichem `task create` wieder löschen.
- **`task copied` vs. `task archive`:** `task copied` hat ein enges
  Versprechen (nur aus `WAITING_FOR_COPY_TO_CONTROL`, explizit geprüft).
  `task archive` ist bewusst weiter gefasst (jeder Zustand, aus dem
  `ARCHIVED` laut Zustandstabelle erreichbar ist) — kein Sonderfall-Code
  nötig, das regelt `state-model.yaml` bereits korrekt.
- **Alte Pakete (001–016) wurden NICHT rückwirkend als echte Bridge-Aufträge
  nacherfasst** — bewusste Entscheidung. Sie bleiben nur als
  `work-packages/*.md`-Dokumente sichtbar, nicht im `bridge board`.

## 7. Offene Punkte / mögliche nächste Schritte

Kein fest geplantes BRIDGE-019 — bewusst offen gelassen. Board,
Befehlsreferenz und Watch-Modus sollen jetzt eine Weile im echten Alltag
laufen, bevor der nächste Ausbauschritt festgelegt wird. Aus der
Vorgänger-Übergabe weiterhin relevant (Abschnitt 7a dort):

1. **Endbild:** dauerhafter manueller Copy-Paste-Dirigent (aktueller Stand)
   vs. später echte API-Vollautomatik (Stufe 3) — bewusst nicht
   vorentschieden.
2. **DORF-Aufträge in der Praxis:** Sobald ein erster echter `DORF-xxxx`-
   Auftrag über `bridge task create` läuft, sollte geprüft werden, ob das
   Projektprofil-Handling (`profiles.load_profile`) und die
   `commands --project dorfschaft`-Pfadauflösung im echten Alltag
   reibungslos funktionieren (bisher nur mit synthetischen Testaufträgen
   geprüft, nie mit einem echten Dorfschaft-Auftrag).
3. **Aktions-Board** (Bridge-Prozesse mit Bestätigung direkt aus dem
   Terminal starten, opt-in) — ursprünglich als eigener späterer Schritt
   gedacht, weiterhin nicht begonnen.

## 8. Delivery-Konvention (ergänzt)

Wie bisher: Browser-Claude liefert pro Paket ein ZIP mit
`work-packages/BRIDGE-xxxx.md` + ggf. Schema-/Datendateien. **Neu seit
BRIDGE-017:** zusätzlich `tasks/incoming/BRIDGE-xxxx.yaml` (Staging-Pfad!)
für Pakete, die selbst über die Bridge laufen sollen. Mensch: `git pull`
zuerst, dann `Expand-Archive ... -Force`, committen, pushen.

## 9. Erste Aktionen im neuen Chat

1. Diese Datei als Kontext nehmen.
2. `origin/main` klonen, Tests laufen lassen, `bridge board` prüfen (sollte
   leer sein).
3. Mit dem Nutzer klären, welcher der drei Punkte aus Abschnitt 7 als
   Nächstes drankommt — oder ob erstmal nur der Alltagsbetrieb beobachtet
   wird, ohne neues Paket.
