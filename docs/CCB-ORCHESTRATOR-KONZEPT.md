# CCB — Konzept: Orchestrator (Reihenfolge-/Ausführungsautomatik)

**Status: Konzept/Diskussionsgrundlage, kein Auftrag, kein Code.** Wird erst
zu `BRIDGE-0027` (o. ä.), wenn die offenen Punkte unten geklärt sind und
`BRIDGE-0026` (Gesamtübersicht) abgeschlossen und verifiziert ist —
Ein-Auftrag-zur-Zeit-Disziplin gilt für Code unverändert.

## Ausgangslage (aus der Steuerchat-Sitzung, 12.09.2026)

Bei mehreren parallel laufenden Projekten auf zwei Maschinen soll die Bridge
nicht nur anzeigen, was passiert (BRIDGE-0026), sondern auch:

1. Vorschlagen und/oder auslösen, was als Nächstes gemacht werden soll —
   **„beides, je nach Auftragsart"**.
2. Bei mehreren gleichzeitig bereiten Aufträgen anhand von
   **Priorität/Dringlichkeit** (neues Feld) entscheiden, was zuerst kommt —
   zusätzlich zu `depends_on` (bereits vorhanden).
3. **In der Web-UI** laufen, auf Basis von BRIDGE-023/024.

## Drei Fragen, die vor einer Spezifikation geklärt sein müssen

### 1. Wo verläuft die Grenze „Vorschlag" vs. „automatischer Auslöser"?

`SECURITY-MODEL.md` Abschnitt 3 („kritische Aktionen nie implizit") gilt
unverändert. Ein Orchestrator, der selbständig `run start`/`task copied`
auslöst, ist selbst eine Aktion mit Konsequenzen. Vorschlag für die
Abgrenzung (zur Diskussion, keine Festlegung):

- **Automatisch auslösen erlaubt:** Aufträge mit `permissions` ⊆
  `[READ_ONLY, WORKTREE_WRITE, TEST_EXECUTION]` — keine Git-Schreib-, keine
  kritischen Rechte. Entspricht dem bereits bestehenden Least-Privilege-
  Grundsatz: reine Lese-/Test-Arbeit braucht keine explizite menschliche
  Freigabe pro Schritt, nur die grundsätzliche Auftragsfreigabe bei
  Erstellung.
- **Nur Vorschlag, nie automatisch:** sobald `GIT_PUSH`, `MERGE`, `DEPLOY`,
  `DATABASE_WRITE`, `FORCE_PUSH`, `PR_CREATE` in `permissions` steht — hier
  entscheidet weiterhin ein Mensch (oder der jeweilige Controller nach
  ausdrücklicher Freigabe, analog `CONTROL.md`).
- **Offene Frage an dich:** Ist diese Grenze richtig gezogen, oder sollte
  sie projektabhängig sein (`project.yaml` bekommt ein
  `orchestrator_policy`-Feld)?

### 2. Priorität/Dringlichkeit — welches Feld, welche Werte, welcher Default?

Schema-Änderung an `task.schema.yaml` (SSOT) — **nicht trivial**, jeder
bestehende Auftrag muss mit einem sinnvollen Default weiterfunktionieren.
Zur Diskussion:

- Einfache Stufen (`LOW`/`MEDIUM`/`HIGH`/`URGENT`), Default `MEDIUM` — analog
  zur bereits vorhandenen `reasoning_level`-Konvention (bekanntes Muster,
  keine neue Systematik).
- Oder eine reine Zahl (z. B. 1–5)?
- **Offene Frage an dich:** Wer setzt die Priorität — der Steuerchat bei
  `task create`, oder soll sie sich aus etwas ableiten (z. B. Alter des
  Auftrags, Anzahl wartender Folgeaufträge über `depends_on`)?
- Zusätzlich zur Priorität: **Maschinen-Kapazität** war in der vorherigen
  Frage explizit *nicht* gewählt — heißt das, zwei Aufträge dürfen
  bewusst gleichzeitig auf derselben Maschine „bereit" sein, und die
  Reihenfolge ist rein eine Anzeige-/Empfehlungsfrage, nicht eine
  technische Sperre? Das sollte hier explizit bestätigt werden, sonst
  entsteht ein Missverständnis.

### 3. Web-UI als Trägerprozess — Konsequenz für „automatisch"

Die Web-UI läuft nur, **solange jemand `webui serve` gestartet hat und das
Fenster offen ist** (`http://127.0.0.1:8420`, hart an localhost gebunden,
kein Hintergrunddienst). Ein „automatischer Auslöser in der Web-UI" bedeutet
also: **nur aktiv, wenn die Web-UI gerade läuft** — kein Auto-Pilot rund um
die Uhr, kein Ersatz für den bereits im Schema vorgesehenen `watch loop`
(eigener Dauerprozess). Das ist wahrscheinlich so gewollt (du hast „Teil der
Web-UI" explizit gewählt, nicht `watch loop`), aber die Konsequenz — kein
24/7-Betrieb ohne offenes Browserfenster — sollte bewusst sein, nicht
nachträglich überraschen.

## Vorgeschlagener grober Aufbau (zur Diskussion, nicht final)

1. `task.schema.yaml`: neues optionales Feld `priority` (Enum oder Zahl,
   Default definiert), rückwärtskompatibel.
2. `project.yaml`-Erweiterung (optional): `orchestrator_policy` — pro
   Projekt einstellbar, ob/wie automatisch ausgelöst werden darf, statt
   einer globalen Regel für alle sieben Projekte gleichermaßen.
3. Neue Funktion (aufbauend auf `bridge overview` aus BRIDGE-0026): aus
   allen „bereiten" Aufträgen (Abhängigkeiten erfüllt, keine Maschinen-
   Kollision — falls doch gewünscht, siehe Frage 2) den nächsten nach
   Priorität auswählen.
4. Je nach Berechtigungsprofil (Frage 1): Button „Vorschlag anzeigen" vs.
   automatischer Trigger-Aufruf der Bridge-CLI aus der Web-UI heraus
   (technisch: derselbe `subprocess`-Mechanismus wie `gitops.py`, aber für
   `bridge run start` statt `git commit`/`push` — neue Whitelist-Logik,
   nicht die bestehende wiederverwenden, da andere Aktion).

## Nicht Teil dieses Konzepts (bewusst abgegrenzt)

- Kein `watch loop`-Dauerprozess (explizit nicht gewählt).
- Keine Änderung an `schemas/state-model.yaml` — der Orchestrator schlägt
  vor/löst aus, erfindet aber keine neuen Zustände.
- Keine Maschinen-Kapazitätssperre (laut Antwort auf Frage „Priorität statt
  Maschinen-Kapazität" — zur Bestätigung siehe Frage 2 oben).
