# CCB — Arbeitsweise des Steuerchats (generell, projektübergreifend)

Dieses Dokument beschreibt **wie** der Steuerchat arbeitet — nicht den
aktuellen Projektstand (dafür: `docs/handover/CCB-UEBERGABE-vX.md`). Es ist bei jedem
neuen Chat zusätzlich zur aktuellsten Übergabe zu lesen, damit
Kommunikationsform, Auftragsdisziplin und Verifikationspflichten nicht
jedes Mal neu erklärt oder fehlerhaft rekonstruiert werden müssen.

**Gilt ab sofort verbindlich, ersetzt keine der Regeln aus `CLAUDE.md`
oder der Übergabedatei, ergänzt sie um die Steuerchat-eigene Seite.**

---

## 1. Sitzungsstart — Pflichtablauf (nicht verkürzbar)

1. Frischen Klon anlegen (`bash_tool`, **nicht** `web_fetch` — liefert für
   dieses Repo zuverlässig 404):
   ```
   rm -rf /home/claude/ccb-session && git clone --quiet \
     https://github.com/zippeliniot/Codex-Control-Bridge.git \
     /home/claude/ccb-session && cd /home/claude/ccb-session && \
     git log --oneline -10
   ```
2. HEAD gegen den in der aktuellsten Übergabedatei genannten Stand
   abgleichen. Weichen sie ab: **zuerst** melden, bevor irgendetwas
   anderes passiert.
3. Die vollständige Übergabedatei **von Anfang bis Ende lesen** — nicht
   nur überfliegen, nicht nur den "Aktueller Stand"-Abschnitt. Abschnitt 0
   (bindende Regeln) ist so bindend wie der Rest.
4. Primärquellen im frischen Klon vollständig lesen, in dieser
   Reihenfolge: `CLAUDE.md` → `docs/architecture/ARCHITECTURE.md` →
   `docs/security/SECURITY-MODEL.md` → `docs/PROJEKTKONZEPT.md` → bei
   Bedarf `CONTROL.md`, `docs/architecture/machines.md`.
5. `schemas/` lesen (mindestens `task.schema.yaml`), nicht aus dem
   Gedächtnis oder aus einer alten Übergabe rekonstruieren.
6. `tasks/` und `work-packages/` frisch aufllisten, höchste vergebene
   `BRIDGE-xxxx`-ID selbst ermitteln — nie eine ID aus einem Dokument
   ungeprüft übernehmen.
7. **Erst danach** den Nutzer begrüßen und mit offenen Schritten
   fortfahren.

**Keine Dichtungen.** Nichts annehmen, ergänzen oder plausibel
erscheinen lassen, was nicht tatsächlich gelesen wurde. Fehlt eine
Datei, ein Abschnitt, ein Wert: das explizit benennen und nachfragen
oder nachlesen — nicht aus Kontext plausibel rekonstruieren. Das gilt
für Code, Schemas, Übergabedateien und für Aussagen des Nutzers über
den Repo-Zustand gleichermaßen (siehe Abschnitt 5, Punkt 2).

---

## 2. Auftragsdisziplin — ein Auftrag zur Zeit

- **Kein neuer Auftrag, solange der letzte nicht vollständig
  abgearbeitet und geprüft ist.** Kein Vorausplanen mehrerer
  BRIDGE-IDs "auf Vorrat". Erst wenn `run finish` durch ist **und** der
  Steuerchat den gepushten Stand per frischem Klon verifiziert hat
  (Abschnitt 5), wird der nächste Auftrag spezifiziert.
- Jede Zustandsänderung eines Auftrags läuft **ausschließlich über die
  Bridge-CLI** (`bridge task create`, `bridge run start`,
  `bridge run beat`, `bridge run finish`, `bridge task copied`,
  `bridge task archive`) — niemals direktes Bearbeiten von Dateien im
  Store, um einen Zustand zu simulieren.
- Für den echten Stand eines Auftrags immer `task show <ID>` und
  `audit show <ID>` nutzen, nie nur `board` (das Board zeigt nur zwei
  Wartezustände, siehe Abschnitt 4).

---

## 3. Kommunikationsform des Steuerchats

- **Alle zu liefernden Dateien** (Work-Packages, Staging-YAMLs, sonstige
  Deliverables) werden **als Datei zum Download erzeugt**
  (`create_file` → `present_files`), **nicht** als Codeblock zum
  Copy-Paste im Chattext. Grund: weniger Fehlerquellen durch
  abgeschnittene Pastes, Encoding-Probleme oder unvollständige
  Übernahme.
- **Jeder Befehl bekommt eine WO-Angabe direkt davor**, nie danach:
  `PowerShell`, `Editor` oder `Claude Code`.
- **PowerShell-Anweisungen** liefert der Steuerchat immer passend zum
  gerade gelieferten Deliverable mit — z. B. Kopierbefehl aus
  `Downloads` an die richtige Repo-Stelle, `git add`/`commit`/`push` für
  das, was tatsächlich ins Repo gehört (nicht für lokale
  Staging-Dateien, siehe `CLAUDE.md`/Übergabe Regel 14).
- **Anweisungen an Claude Code** enthalten **immer und unübersehbar**
  (als eigener hervorgehobener Block, nicht im Fließtext versteckt):
  1. Pflicht zur Nutzung der Bridge-CLI für jede Zustandsänderung.
  2. Pflicht zu `git push` am Ende, wenn `GIT_PUSH` im
     Berechtigungsprofil steht — ohne Push kann der Steuerchat das
     Ergebnis nicht per frischem Klon abrufen und prüfen.
- **Step by step:** ein Arbeitsschritt/eine Entscheidung nach der
  anderen, nicht mehrere Optionen gleichzeitig zur Auswahl stellen, wenn
  eine sinnvolle Standardentscheidung getroffen werden kann — dann
  Annahme kurz benennen und weitermachen, statt zu blockieren.

---

## 4. CCB-Nutzung — Kurzreferenz

- **CLI-Aufrufform:** `.venv\Scripts\python.exe src\bridge\cli.py --root .
  --schema-dir schemas <befehl>` — kein global installiertes `bridge`-Kommando.
- **Board zeigt nur** `WAITING_FOR_HANDOFF_TO_EXECUTOR` und
  `WAITING_FOR_COPY_TO_CONTROL`. Läuft/geclaimte Aufträge (`RUNNING`,
  `CLAIMED`) erscheinen dort **nicht** — ein leeres Board heißt nicht
  "nichts passiert".
- **Ein Store-Eintrag entsteht ausschließlich über**
  `bridge task create <path-zur-staging-yaml>` — niemals durch bloßes
  Ablegen einer YAML-Datei im Dateisystem. Der Auto-Chain-Mechanismus
  legt den tatsächlichen Startstatus fest, nicht zwingend der
  `status:`-Wert aus der Staging-YAML — danach immer `task show <ID>`
  prüfen.
- **Staging-Pfad:** `tasks/incoming/<ID>.yaml` — existiert nicht im
  Git-Repo selbst (lokal angelegt/`.gitignore`d), kein Fehler, wenn es
  im frischen Klon fehlt.
- **`GIT_PUSH`** ist nur bei `bridge task create` festlegbar (kein
  `task edit`) — muss also **vorab** in der Staging-YAML stehen, sonst
  bleibt Push für den ganzen Auftrag Mensch-Aktion.
- **`--force`-Push ist immer verboten**, unabhängig vom
  Berechtigungsprofil.
- **RUN-Nummern sind kein Ort/keine Maschine** — reine Zähler innerhalb
  einer `bridge_task_id`. Bei Unklarheit, welches Fenster an welchem
  Auftrag arbeitet, aktiv nachfragen.
- **`run finish` niemals ohne `--summary`** — sonst bleibt `result.yaml`
  ohne auswertbaren Inhalt.
- **`--commit`-Flag (ab BRIDGE-025):** auf `task create`, `run start`,
  `run finish`, `task copied`, `task archive` verfügbar. Committet lokal
  (kein Push) ausschließlich die von der Store-Funktion geschriebenen
  Dateien — per Whitelist fail-closed, Branch-Check (`main`), kein Force-Push.
  **Sollte der Standardweg für Ops-Commits in Claude-Code-Läufen sein**,
  statt manuelles `git add` mit der Gefahr, eine Datei zu vergessen.
  Bei Whitelist- oder Branch-Fehler: Exit-Code 3, Store-Aktion bleibt.
- **`--base-head` bei `run finish` (ab BRIDGE-025):** Fehlt das Flag,
  wird `git.expected_head` aus `task.yaml` automatisch abgeleitet. Fehlt
  auch das, bricht der Befehl fail-closed ab (Exit-Code 1). Das Feld
  `git.expected_head` **muss** daher in der Staging-YAML stehen — es
  enthält den HEAD-SHA zum Zeitpunkt der Auftragsanlage und sichert, dass
  `changed_files` in `result.yaml` den **gesamten Lauf** abdeckt
  (Bugfix für BRIDGE-023/024).

---

## 5. Verifikationspflichten des Steuerchats

1. **Git-Aussagen des Nutzers ("gepusht", "fertig") nie ungeprüft
   glauben.** Nach jeder gemeldeten Aktion: frischer `git clone` in ein
   Scratch-Verzeichnis via `bash_tool`, `git log --oneline` vergleichen,
   Inhalt der behaupteten Änderung tatsächlich lesen — erst danach den
   nächsten Schritt vorschlagen.
2. **Gilt auch umgekehrt:** meldet ein Tool "alles ok", obwohl der
   vorherige Status etwas anderes nahelegte, nicht vorschnell
   "Fehlalarm" rufen — den tatsächlichen Zielzustand direkt prüfen.
3. **Work-Package-Annahmen gegen den echten Funktionscode prüfen**, nicht
   nur gegen Schema/Doku — vor jeder Spezifikation, die auf einer
   bestimmten CLI-Operation aufbaut, den Funktionskörper in
   `src/bridge/*.py` lesen.
4. **Nachtest-Seiteneffekte:** schlägt ein Fund/Fix-Auftrag einen
   "Nachtest gegen einen echten anderen Auftrag" vor, danach immer auch
   den Audit-Trail dieses anderen Auftrags prüfen.
5. **Diagnosebefehle im echten Arbeitsverzeichnis**, nicht in einem
   Verifikations-Scratch-Klon — Store-verändernde Befehle dürfen dort
   nicht laufen (kein `.venv`, kein echter Store).
6. **Push-Fähigkeit des Steuerchats selbst nicht annehmen.** Der
   Steuerchat hat in dieser Sandbox **keine** Push-Credentials für
   `github.com` (kein Git-Identity/Token konfiguriert) — geprüft per
   `git push --dry-run`. Alle ins Repo gehenden Deliverables (v. a.
   `work-packages/*.md`) werden dem Nutzer als Datei geliefert, der sie
   selbst per PowerShell committet und pusht. Kein "ich lege das schon
   ins Repo"-Versprechen, das nicht eingehalten werden kann.

---

## 6. Wann diese Datei aktualisiert wird

Dieses Dokument beschreibt Arbeitsweise, nicht Zustand — es ändert sich
nur, wenn sich die **Art der Zusammenarbeit** ändert (neue
Kommunikationsregel, neue Verifikationspflicht, neue CCB-Mechanik). Der
laufende Projektstand (offene BRIDGE-IDs, nächste Schritte) gehört
weiterhin ausschließlich in die jeweils aktuelle
`docs/handover/CCB-UEBERGABE-vX.md`.
