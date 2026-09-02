#!/usr/bin/env bash
#
# handover-check.sh — Übergabe-Gate der Codex Control Bridge.
# Prüft fail-closed, ob der aktuelle Stand vollständig auf GitHub liegt.
# Vor JEDEM Maschinenwechsel ausführen (siehe docs/handover/HANDOVER.md).
#
# Exit 0 = PASS (Übergabe zulässig), Exit != 0 = FAIL (Übergabe NICHT zulässig).
#
# Nutzung:
#   bash scripts/handover-check.sh            # Übergabebranch = main
#   bash scripts/handover-check.sh <branch>   # abweichender Übergabebranch

set -u

EXPECTED_BRANCH="${1:-main}"
FAIL=0
note()  { printf '  %s\n' "$1"; }
ok()    { printf '[ OK ]   %s\n' "$1"; }
bad()   { printf '[ FAIL ] %s\n' "$1"; FAIL=1; }
warn()  { printf '[ WARN ] %s\n' "$1"; }

echo "=== Codex Control Bridge — Handover Check ==="

# 0) Git-Repository vorhanden?
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  bad "Kein Git-Repository. Abbruch."
  exit 1
fi

# 1) Aktueller Branch = Übergabebranch?
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" = "$EXPECTED_BRANCH" ]; then
  ok "Branch = $EXPECTED_BRANCH"
else
  bad "Branch ist '$CURRENT_BRANCH', erwartet '$EXPECTED_BRANCH'"
fi

# 2) Working Tree sauber (keine uncommitted Änderungen)?
if [ -z "$(git status --porcelain --untracked-files=no)" ]; then
  ok "Working Tree sauber (keine offenen Änderungen)"
else
  bad "Uncommitted Änderungen vorhanden:"
  git status --short --untracked-files=no | sed 's/^/         /'
fi

# 3) Keine untracked Dateien (gingen beim Wechsel verloren)?
UNTRACKED="$(git ls-files --others --exclude-standard)"
if [ -z "$UNTRACKED" ]; then
  ok "Keine untracked Dateien"
else
  bad "Untracked Dateien vorhanden (nicht auf GitHub):"
  echo "$UNTRACKED" | sed 's/^/         /'
fi

# 4) Keine offenen Stashes?
if [ -z "$(git stash list)" ]; then
  ok "Keine offenen Stashes"
else
  bad "Offene Stashes vorhanden (nicht auf GitHub):"
  git stash list | sed 's/^/         /'
fi

# 5) Remote-Abgleich: lokal darf NICHT ahead von origin sein.
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --quiet origin "$EXPECTED_BRANCH" 2>/dev/null || warn "git fetch fehlgeschlagen — Remote-Vergleich evtl. veraltet"
  if git rev-parse --verify --quiet "origin/$EXPECTED_BRANCH" >/dev/null; then
    AHEAD="$(git rev-list --count "origin/$EXPECTED_BRANCH..HEAD" 2>/dev/null || echo '?')"
    BEHIND="$(git rev-list --count "HEAD..origin/$EXPECTED_BRANCH" 2>/dev/null || echo '?')"
    if [ "$AHEAD" = "0" ]; then
      ok "Alles gepusht (lokal nicht ahead von origin/$EXPECTED_BRANCH)"
    else
      bad "$AHEAD Commit(s) nicht gepusht -> 'git push origin $EXPECTED_BRANCH' nötig"
    fi
    if [ "$BEHIND" != "0" ]; then
      warn "$BEHIND Commit(s) auf origin, die lokal fehlen (ggf. erst pullen)"
    fi
  else
    bad "origin/$EXPECTED_BRANCH nicht gefunden — wurde der Branch je gepusht?"
  fi
else
  bad "Kein 'origin' konfiguriert — GitHub-Remote fehlt"
fi

# 6) Pflichtdokumente (fachliche Arbeitsgrundlage) vorhanden?
REQUIRED_DOCS="docs/PROJEKTKONZEPT.md docs/architecture/ARCHITECTURE.md docs/handover/HANDOVER.md docs/architecture/machines.md"
for d in $REQUIRED_DOCS; do
  if [ -f "$d" ] && git ls-files --error-unmatch "$d" >/dev/null 2>&1; then
    ok "Pflichtdokument versioniert: $d"
  else
    bad "Pflichtdokument fehlt oder nicht versioniert: $d"
  fi
done

echo "============================================"
if [ "$FAIL" -eq 0 ]; then
  echo "ERGEBNIS: PASS — Übergabe zulässig."
  exit 0
else
  echo "ERGEBNIS: FAIL — Übergabe NICHT zulässig. Erst alles committen und pushen."
  exit 1
fi
