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
- **RUN-01 ist rein lesend** (`GET /`, `GET /api/board`); jede andere
  Methode/Route antwortet 404/405. Ein Store-/Profilfehler wird als
  JSON-Fehlerobjekt mit HTTP 500 zurückgegeben und beendet den Server
  nicht.
- Schreibende Aktions-Endpunkte folgen erst in RUN-02 — mit
  serverseitiger Bestätigungspflicht und Same-Origin-Prüfung, nicht nur
  einem Browser-Dialog.

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
