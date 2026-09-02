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
