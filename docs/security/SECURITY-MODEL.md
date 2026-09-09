# Sicherheitsmodell — Codex Control Bridge

> **Status:** verbindlich ab BRIDGE-001.

## 1. Grundsatz: Least Privilege

Die Bridge erhält **niemals allein aufgrund eines eingegangenen Auftrags**
unbeschränkte Rechte. Jeder Auftrag trägt ein explizites Berechtigungsprofil.

**Default:**

```
READ_ONLY
```

Erweiterte Rechte müssen ausdrücklich im Auftrag vorhanden sein.

## 2. Rechtestufen

```
READ_ONLY
WORKTREE_WRITE
TEST_EXECUTION
GIT_STAGE
GIT_COMMIT
GIT_PUSH
PR_CREATE
MERGE
DEPLOY
DATABASE_WRITE
```

## 3. Kritische Aktionen — nie implizit

Die folgenden Aktionen dürfen **nur** bei ausdrücklicher, auftragsgebundener
Freigabe erfolgen und niemals aus einer schwächeren Stufe abgeleitet werden:

```
MERGE
DEPLOY
DATABASE_WRITE
FORCE_PUSH
MIGRATION_PRODUCTION
```

## 4. Fail-closed

Bei jeder der folgenden Situationen wird der Auftrag `BLOCKED` — die Bridge
improvisiert nicht:

- falscher Worktree
- unerwarteter HEAD
- unbekannter Auftrag
- Ergebnis für falsche Task-ID
- unerlaubte Git-Aktion
- nicht eindeutige Maschinenidentität
- beschädigte Task-Datei
- Schemafehler

## 5. Git-Sicherheit

Der Git-Zustand ist Teil der Auftragsidentität. Vor einem Lauf mindestens:

```
repository · branch · HEAD · upstream · ahead/behind · worktree status · index status
```

Bei relevanten Aufträgen zusätzlich:

```
expected_head · allowed_changed_files · expected_diff_hash
```

Stimmt die erwartete Ausgangslage nicht, bricht der Auftrag ab (fail-closed).

## 5a. Web-UI (BRIDGE-020)

Die lokale Web-UI (`bridge webui serve`) ist eine dünne Anzeige- und
Bedienschicht über den bereits abgesicherten Store-/Runner-Funktionen.

- **Bindung ausschließlich an `127.0.0.1`.** Kein `0.0.0.0`, keine
  `--host`-Option — die Adresse ist im Code hart verdrahtet
  (`webui.HOST`). Das ist die technische Umsetzung von „keine externe
  Erreichbarkeit", nicht nur eine Empfehlung: ein Aufweichen der Bindung
  würde die ungeschützte Bridge-Steuerung für das gesamte Netz öffnen.
- **Kein Auth-Layer.** Bewusst, weil der Dienst nur lokal auf einer
  Ein-Nutzer-Maschine erreichbar ist. Diese Lücke ist hier ausdrücklich
  dokumentiert, damit niemand später `--host 0.0.0.0` ergänzt, ohne das
  fehlende Login zu bedenken.
- **Lesend** (`GET /`, `GET /api/board`): jede unbekannte Route/Methode
  antwortet 404/405. Ein Store-/Profilfehler wird als JSON-Fehlerobjekt
  mit HTTP 500 zurückgegeben und beendet den Server nicht.
- **Schreibende Aktions-Endpunkte** (`POST /api/task/<id>/copied`,
  `POST /api/task/<id>/archive`, `POST /api/run/<id>/finish`) rufen
  dieselbe Store-/Runner-Logik wie die entsprechenden CLI-Kommandos auf
  (kein Parallel-Code, kein eigener Audit-Pfad). Zusätzlich abgesichert:
  - **Serverseitige Bestätigungspflicht:** ohne `confirm: true` und ohne
    nicht-leeren `actor` → HTTP 400. Der Browser-Dialog ist nur UX; ein
    `curl`-Aufruf ohne `confirm` löst nichts aus.
  - `run finish` zusätzlich: ohne nicht-leere `summary` → HTTP 400
    (setzt die `--summary`-Pflicht aus `CLAUDE.md` / BRIDGE-021 durch).
  - **Same-Origin-Prüfung:** `Origin` (ersatzweise `Referer`) jedes
    `POST` muss `http://127.0.0.1:<port>` sein, sonst HTTP 403 — Schutz
    gegen einen fremden Browser-Tab, der im Hintergrund gegen `localhost`
    postet. Kein CSRF-Token (Single-User, kein Login), aber nicht
    optional.
  - Eine im aktuellen Zustand unzulässige Aktion wird mit HTTP 409 und
    derselben Fehlermeldung wie im CLI abgelehnt (nicht stillschweigend
    ignoriert).

## 6. Grenzen der ersten Version (Nicht-Ziele)

Zunächst ausdrücklich **nicht** vorgesehen:

- selbstständige fachliche Projektentscheidungen
- automatische Freigabe kritischer Git-Aktionen
- automatisches Merge in `main`
- autonomes Deployment
- produktive Datenbankänderungen
- automatische Architektur- oder Sicherheitsfreigaben
- unkontrollierter Zugriff auf beliebige Repositories
- direkte Manipulation laufender Chats ohne vorgesehene Schnittstelle
