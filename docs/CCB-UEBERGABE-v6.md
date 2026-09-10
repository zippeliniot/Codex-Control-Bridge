# CCB — Übergabe an neuen Steuerchat (Stand: 10.09.2026, nach BRIDGE-020/022/023/024/025)

Dieses Dokument ersetzt `CCB-UEBERGABE-v5.md` als aktuellen Übergabestand.
**Abschnitt 0 ist bindend, nicht optional.** Neu seit v5: Punkt 15
(Verweis auf `CCB-STEUERCHAT-ARBEITSWEISE.md`), Punkt 16 (Web-UI kann
jetzt selbst committen/pushen), Punkt 17 (`--commit`-Flag der CLI).

## Abschnitt 0 — Bindende Regeln

1. **CLI-Aufrufform:** `.venv\Scripts\python.exe src\bridge\cli.py --root .
   --schema-dir schemas <befehl>` — nicht `bridge <befehl>` direkt (kein
   global installiertes Kommando).
2. **`git reset --hard` nach jedem `git fetch`**, bevor irgendetwas
   Inhaltliches gemacht wird — Ausgangslage muss exakt `origin/main`
   entsprechen, nicht nur "gefetcht".
3. **Kein `git add -A` bei parallelen Aufträgen.** Immer gezielt stagen
   (`git add <konkrete Pfade>`), sonst landen Store-Änderungen eines
   anderen, parallel laufenden Auftrags im falschen Commit. Seit
   BRIDGE-025 übernimmt `--commit` (Punkt 17) das automatisch und
   korrekt für Store-Aktionen — für sonstige Commits gilt die Regel
   unverändert manuell.
4. **Push ist grundsätzlich Mensch-Aktion**, außer der Auftrag trägt
   `GIT_PUSH` ausdrücklich im Berechtigungsprofil
   (`docs/security/SECURITY-MODEL.md` Abschnitt 2) — dann darf Claude
   Code selbst pushen (über die `.claude/settings.json`-Ask-Bestätigung,
   siehe Punkt 15/`auto`-Modus). `--force`-Push ist **immer** verboten,
   in jedem Kontext, ohne Ausnahme. Berechtigungen sind nur bei
   `bridge task create` festlegbar, **kein** `task edit` vorhanden —
   `GIT_PUSH` muss vorab in der Staging-YAML (`tasks/incoming/<ID>.yaml`,
   siehe Punkt 14) stehen. **Ausnahme seit BRIDGE-024:** Die
   Web-UI-Aktionen (`copied`/`archive`/`finish`-Buttons) committen und
   pushen jetzt automatisch selbst, siehe Punkt 16 — das ist eine
   bewusste, dokumentierte Ausnahme von "Push ist Mensch-Aktion", nicht
   ein Widerspruch dazu.
5. **Board zeigt laufende Aufträge (`RUNNING`/`CLAIMED`) niemals an** —
   nur die beiden Wartezustände `WAITING_FOR_HANDOFF_TO_EXECUTOR` und
   `WAITING_FOR_COPY_TO_CONTROL`. Ein leeres/unvollständiges Board heißt
   nicht "nichts passiert", sondern oft "etwas läuft gerade woanders".
   Für den echten Stand immer `task show <ID>` und `audit show <ID>`
   nutzen, nicht nur `board`.
6. **Git-Aussagen des Nutzers immer per frischem Klon verifizieren, nie
   ungeprüft glauben.** Nach jeder gemeldeten Push-Aktion selbst
   `git clone` in ein Scratch-Verzeichnis (`bash_tool`), `git log
   --oneline` vergleichen, Inhalt der behaupteten Änderung tatsächlich
   lesen. Erst danach den nächsten Schritt vorschlagen. **Gilt genauso
   umgekehrt:** wenn ein Tool/Kommando "alles ok"/"up to date" meldet,
   obwohl der vorherige Status etwas anderes nahelegte, nicht vorschnell
   "Fehlalarm" rufen — den tatsächlichen Zielzustand direkt im echten
   Arbeitsverzeichnis prüfen, bevor man urteilt. In dieser Sitzung
   mehrfach real aufgetreten (BRIDGE-0023 „fertig" gemeldet, war es
   nicht; BRIDGE-0024 `task.yaml` fehlte im Commit trotz „gepusht") —
   diese Regel ist keine Formalie, sie hat wiederholt echte Fehler
   gefangen.
7. **Work-Package-Annahmen gegen den tatsächlichen Funktionscode prüfen,
   nicht nur gegen `state-model.yaml`/Schema.** Vor dem Schreiben einer
   Spezifikation, die auf einer bestimmten CLI-Operation aufbaut, immer
   den Funktionskörper in `src/bridge/*.py` lesen, nicht nur Schema/Doku.
8. **"Manuelle Nachtests" in einem Auftrag können echte
   Zustandsänderungen an einem *anderen* Auftrag auslösen.** Bei jedem
   Fund/Fix-Auftrag, der einen "Nachtest gegen einen echten anderen
   Auftrag" vorschlägt, danach IMMER den Audit-Trail dieses anderen
   Auftrags mitprüfen (`audit show <ID>`), nicht nur den Fix-Auftrag
   selbst — sonst übersieht man Seiteneffekte.
9. **RUN-Nummern sind kein Ort.** `RUN-01`/`RUN-02` etc. sind reine
   Zähler innerhalb einer `bridge_task_id`, keine Maschinen-/Fenster-
   Kennung. Mehrere Claude-Code-Fenster können parallel an verschiedenen
   BRIDGE-IDs arbeiten — welches Fenster an welchem Auftrag arbeitet,
   weiß nur der Mensch, die Bridge trackt das nicht fensterscharf. Bei
   Unklarheit aktiv nachfragen, in welchem Fenster was läuft.
10. **Format-Präferenz des Nutzers:** Alle Anweisungen (PowerShell-
    Befehle, Editor-Einfügetexte, Claude-Code-Prompts) immer klar
    copy-paste-fähig ausgeben, mit **WO**-Angabe (PowerShell / Editor /
    Claude Code) direkt davor, nie danach. **Seit dieser Sitzung
    zusätzlich:** alle zu liefernden Dateien (Work-Packages,
    Staging-YAMLs) werden **als Datei zum Download** erzeugt
    (`create_file`→`present_files`), nicht als Copy-Paste-Codeblock im
    Chattext — siehe Punkt 15.
11. **Repo-Dateien (Docs, Code, Diffs) über `bash_tool` mit `git clone`
    lesen, NICHT über `web_fetch`.** `web_fetch` liefert für
    `https://github.com/zippeliniot/Codex-Control-Bridge` zuverlässig
    einen 404, obwohl das Repo öffentlich ist. `bash_tool` mit
    `git clone --quiet https://github.com/zippeliniot/Codex-Control-Bridge.git
    /home/claude/<name> && cd /home/claude/<name> && cat <datei>`
    funktioniert zuverlässig und ist der Standardweg.
12. **Primärquellen am Sitzungsanfang vollständig frisch lesen,
    nicht auf fragmentarische Notizen/frühere Übergabe-Auszüge
    verlassen.** `CLAUDE.md`, `docs/architecture/ARCHITECTURE.md`,
    `docs/security/SECURITY-MODEL.md`, `docs/PROJEKTKONZEPT.md`,
    `docs/CCB-STEUERCHAT-ARBEITSWEISE.md` (und bei Bedarf `CONTROL.md`,
    `docs/architecture/machines.md`) vollständig lesen (via Punkt 11),
    bevor ein neuer Auftrag spezifiziert oder eine Regel zitiert wird.
    Nummernvergabe für `bridge_task_id` ist Aufgabe des Steuerprozesses
    (dieses Chats) — vor jeder neuen ID `task list` (oder `ls tasks/`
    im frischen Klon) prüfen, welche IDs bereits vergeben sind, nie eine
    ID annehmen oder erfinden.
13. **Bei Diagnosebefehlen (`git log`/`git status`/`task show`)
    immer sicherstellen, dass sie im echten Arbeitsverzeichnis laufen,
    nicht in einem Scratch-/Verifikations-Klon.** Ein Verifikations-Klon
    ist ein separates Verzeichnis — Store-verändernde Befehle wie
    `task archive` dürfen dort nicht ausgeführt werden.
14. **Ein Store-Eintrag entsteht ausschließlich über
    `bridge task create <path-zur-yaml>`, niemals durch bloßes Ablegen
    einer YAML-Datei im Dateisystem.** Staging-Pfad:
    `tasks/incoming/<ID>.yaml` — seit BRIDGE-024 in `.gitignore`
    eingetragen (`tasks/incoming/`), damit Staging-Dateien nicht mehr
    versehentlich committet werden (war bei BRIDGE-0024 real passiert,
    per Steuerchat-Nachtrag korrigiert). Der Auto-Chain-Mechanismus legt
    den tatsächlichen Startstatus fest — vor jedem Testauftrag den
    echten resultierenden Zustand per `task show <ID>` prüfen.
15. **NEU — `docs/CCB-STEUERCHAT-ARBEITSWEISE.md` lesen und befolgen.**
    Separates, generelles Dokument (nicht projektstandspezifisch), das
    beschreibt *wie* der Steuerchat arbeitet: Sitzungsstart-Pflichtablauf,
    Ein-Auftrag-zur-Zeit-Disziplin, Datei-statt-Copy-Paste-Konvention,
    Bridge-Nutzung, Verifikationspflichten — inklusive der Erkenntnis,
    dass der Steuerchat in seiner Sandbox **keine Push-Credentials** für
    `github.com` hat (`git push --dry-run` schlägt fehl) und deshalb
    Deliverables immer als Datei liefert, nie selbst committet/pusht.
16. **NEU — Web-UI committet und pusht jetzt selbst (BRIDGE-024).** Die
    drei Aktions-Buttons (`Kopiert → Review`, `Archivieren`, `Lauf
    abschließen`) führen nach erfolgreicher Store-Aktion automatisch
    `git commit` **und** `git push` aus — abgesichert durch eine feste
    Datei-Whitelist pro Aktionstyp (fail-closed bei unerwarteten
    Änderungen, kein `git add -A`), Branch-Prüfung (nur `main`) und
    kategorischem `--force`-Verbot. Dokumentiert in
    `SECURITY-MODEL.md` Abschnitt 5b. **Praktische Folge:** nach einem
    Web-UI-Klick ist in der Regel **kein** manuelles PowerShell mehr
    nötig — der persistente Aktions-Log in der UI zeigt das Git-Ergebnis
    direkt an (`→ committed <sha>, gepusht`).
17. **NEU — CLI-`--commit`-Flag (BRIDGE-025), nur lokal, kein Push.**
    Vorhanden auf `task create`, `run start`, `run finish`, `task
    copied`, `task archive`. Nutzt dieselbe Whitelist-Logik wie Punkt 16
    (`src/bridge/gitops.py`, gemeinsames Modul für Web-UI und CLI), aber
    **ohne** automatischen Push — Push bleibt hier Mensch-/
    `GIT_PUSH`-Sache (Punkt 4). **Claude Code soll dieses Flag ab jetzt
    standardmäßig bei jedem state-ändernden `bridge`-Aufruf nutzen**,
    statt Dateien manuell per `git add` zu bestimmen — genau das hat
    zweimal (BRIDGE-023, BRIDGE-024) zu unvollständigen Commits geführt,
    bevor der Fix kam. Zusätzlich: `--base-head` bei `run finish` wird,
    falls nicht explizit gesetzt, automatisch aus `task.yaml` →
    `git.expected_head` abgeleitet; fehlt auch das, bricht der Befehl
    fail-closed ab (Exit-Code 1) statt still ein unvollständiges
    `changed_files` zu erzeugen (Exit-Code 3 bei Whitelist-Verstoß im
    `--commit`-Pfad).

## Aktueller Stand (verifiziert per frischem Klon via `bash_tool`, HEAD `0410748`)

Alle Aufträge `BRIDGE-0017` bis `BRIDGE-0025` sind **`ARCHIVED`**.
Höchste vergebene ID: `BRIDGE-0025` (Store und `work-packages/`
stimmen überein) — **nächste freie ID: `BRIDGE-0026`**.

- **BRIDGE-0020** (Web-UI Stufe 1+2, Lese-Board + Aktions-Buttons):
  `ARCHIVED`. Im Browser durchgeklickt und funktionsfähig bestätigt
  (mehrfach, u. a. via Screenshots in dieser Sitzung).
- **BRIDGE-0022** (`runner.resume()` um `REVIEW_REQUIRED` erweitert):
  `ARCHIVED`, unverändert aus v5-Übergabe.
- **BRIDGE-0023** (Web-UI: Auto-Refresh-Härtung, persistenter
  Aktions-Log, clientseitige Filter): `ARCHIVED`. Bei der Prüfung
  gefunden und korrigiert: `result.yaml` → `changed_files` war
  unvollständig (Ursache erst bei BRIDGE-025 strukturell behoben).
- **BRIDGE-0024** (Web-UI committet/pusht Aktionen selbst): `ARCHIVED`.
  Live im Browser getestet, nicht nur per Unit-Test — Log zeigte
  `committed <sha>, gepusht`, per frischem Klon verifiziert. Bei der
  Prüfung gefunden und korrigiert: `tasks/BRIDGE-0024/task.yaml` fehlte
  im `run-finish`-Commit (Steuerchat-Nachtrag), `tasks/incoming/
  BRIDGE-0024.yaml` wurde versehentlich mit committet (per `.gitignore`
  behoben, siehe Punkt 14).
- **BRIDGE-0025** (CLI härten: `gitops.py`, `--commit`-Flag,
  `base_head`-Fail-closed): `ARCHIVED`. Behebt beide oben genannten
  Root-Causes strukturell, nicht nur punktuell. Bei der Prüfung
  verifiziert: `changed_files` des eigenen Laufs war vollständig (13
  Dateien), der per `--commit` erzeugte Dogfooding-Commit enthielt
  `task.yaml` korrekt — der Fix hat sich am eigenen Auftrag bewährt.
- Testsuite-Stand: **246 Tests**, frisch im isolierten `.venv` gelaufen
  und grün (nicht nur aus Diff-Umfang plausibilisiert).
- **Claude Code läuft als native Windows-App** (nicht zwingend über ein
  separates PowerShell-Fenster) — Arbeitsverzeichnis
  `E:\_DEV\Codex-Control-Bridge`. Empfohlener Berechtigungsmodus:
  `auto` (Classifier-basiert, reduziert Rückfragen stark, blockiert
  weiterhin Force-Push/Deploy/Migration u. ä.) statt „Berechtigungen
  umgehen" (`bypassPermissions`) — Letzteres ist laut offizieller Doku
  nur für isolierte Container/VMs ohne Internetzugang vorgesehen, nicht
  für diese native Windows-Maschine mit echtem Internetzugang.

## Nicht von selbst anfangen bei

- Codex-/ChatGPT-Aktivierung (`CONTROL.md`) — wartet auf physische
  Umgebungseinrichtung durch den Nutzer.
- `review_roles`-Durchsetzung — bewusst zurückgestellt.

## Offene nächste Schritte

Keine zwingend nächsten Schritte aus dieser Sitzung offen — alle drei
Aufträge (BRIDGE-023/024/025) vollständig abgeschlossen und verifiziert.
Nächster Auftrag (`BRIDGE-0026`) noch nicht besprochen; erst
spezifizieren, wenn der Nutzer ein konkretes Anliegen nennt (Ein-
Auftrag-zur-Zeit-Disziplin, Punkt 3 der `CCB-STEUERCHAT-ARBEITSWEISE.md`
gilt unverändert).
