"""Git-Commit-Logik fuer Store-Aktionen (BRIDGE-025).

Gemeinsames Modul fuer Web-UI und CLI. Kapselt Datei-Whitelist-Pruefung,
Branch-Check und den eigentlichen git-Subprozess.

Sicherheitsleitplanken (nicht verhandelbar, BRIDGE-024 Sicherheitsentscheid):
- Force-Push (weder force noch force-with-lease) kommt in diesem Modul nicht vor.
- ``git add -A`` kommt nicht vor; nur konkrete Pfade werden gestaged.
- Branch muss ``main`` sein, sonst Abbruch.
- Unerwartete Aenderungen ausserhalb der Whitelist -> Abbruch ohne Commit.

Oeffentliches API:
- ``expected_git_files(kind, task_id, run_id=None) -> list[str]``
- ``matches_whitelist(path, whitelist) -> bool``
- ``git_commit(repo_root, kind, task_id, actor, run_id=None, push=True,
               source='Web-UI') -> dict``
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_GIT_TIMEOUT = 30       # Sekunden, Timeout fuer lokale git-Kommandos
_GIT_PUSH_TIMEOUT = 60  # Sekunden, Timeout fuer git push (Netz)


def expected_git_files(kind: str, task_id: str,
                       run_id: str | None = None) -> list[str]:
    """Erlaubte Datei-Whitelist pro Aktionstyp.

    Eintraege ohne abschliessendes '/' sind exakte Pfade; Eintraege mit '/'
    sind Praefix-Matches (alles darunter ist erlaubt).

    Web-UI-Arten:
        ``finish``, ``copied``, ``archive``

    CLI-Arten:
        ``task_create``, ``run_start``, ``run_finish``,
        ``task_copied``, ``task_archive``
    """
    base = [f"tasks/{task_id}/task.yaml", "audit/audit.jsonl"]

    if kind in ("finish", "run_finish"):
        if run_id:
            # Alles unter dem Lauf-Verzeichnis (result.yaml, heartbeat.json, ...)
            base.append(f"results/{task_id}/{run_id}/")
        # Work-Package wird ggf. mit Checkbox-Aenderungen committet
        base.append(f"work-packages/{task_id}.md")

    elif kind == "run_start":
        if run_id:
            # Heartbeat-Datei (results/<id>/<run_id>/heartbeat.json)
            base.append(f"results/{task_id}/{run_id}/")

    # 'copied', 'archive', 'task_create', 'task_copied', 'task_archive'
    # benoetigen nur base (task.yaml + audit.jsonl)

    return base


def matches_whitelist(path: str, whitelist: list[str]) -> bool:
    """True, wenn ``path`` exakt oder als Praefix (Eintrag endet mit '/') passt."""
    for allowed in whitelist:
        if allowed.endswith("/"):
            if path.startswith(allowed):
                return True
        elif path == allowed:
            return True
    return False


def git_commit(repo_root, kind: str, task_id: str, actor: str,
               run_id: str | None = None, push: bool = True,
               source: str = "Web-UI") -> dict:
    """Nach einer Store-Aktion: Branch pruefen, Whitelist pruefen,
    nur die erwarteten Dateien stagen, committen, optional pushen.

    Sicherheitsleitplanken (nicht verhandelbar, BRIDGE-024 Sicherheitsentscheid):
    - Force-Push (weder force noch force-with-lease) kommt nicht vor.
    - ``git add -A`` kommt nicht vor; nur konkrete Pfade werden gestaged.
    - Branch muss ``main`` sein, sonst Abbruch.
    - Unerwartete Aenderungen ausserhalb der Whitelist -> Abbruch ohne Commit.

    Parameter:
        repo_root: Wurzelverzeichnis des Git-Repos.
        kind:      Aktionstyp (z.B. 'finish', 'task_create', 'run_finish').
        task_id:   Bridge-Auftrags-ID.
        actor:     Ausfuehrender Akteur (nur fuer commit-Nachricht genutzt).
        run_id:    Lauf-ID (z.B. 'RUN-01'), nur noetig fuer Arten mit Lauf-Dateien.
        push:      True  -> pushen (Web-UI-Standard);
                   False -> nur lokal committen (CLI-Standard, kein Netzwerk).
        source:    Klartext fuer die Commit-Nachricht, z.B. 'Web-UI' oder 'CLI'.

    Gibt immer ein dict ``{committed, commit, pushed, error}`` zurueck.
    Fehler im Git-Teil lassen die Store-Aktion unangetastet.
    """
    root = Path(repo_root)

    def _run(args, timeout=_GIT_TIMEOUT):
        return subprocess.run(
            args, cwd=root, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8",
        )

    # 1. Branch-Pruefung — nur 'main' ist erlaubt.
    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if r.returncode != 0:
        return {"committed": False, "commit": None, "pushed": False,
                "error": f"git rev-parse fehlgeschlagen: {r.stderr.strip()}"}
    branch = r.stdout.strip()
    if branch != "main":
        return {"committed": False, "commit": None, "pushed": False,
                "error": (f"Branch-Pruefung fehlgeschlagen: aktueller Branch ist "
                          f"'{branch}', erwartet 'main'.")}

    # 2. git status --porcelain: alle geaenderten/unverfolgten Dateien ermitteln.
    r = _run(["git", "status", "--porcelain", "--untracked-files=all"])
    if r.returncode != 0:
        return {"committed": False, "commit": None, "pushed": False,
                "error": f"git status fehlgeschlagen: {r.stderr.strip()}"}

    changed: list[str] = []
    for line in r.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]                    # 'XY ' prefix abschneiden
        if " -> " in path:                 # Umbenennungen: nur Ziel nehmen
            path = path.split(" -> ", 1)[1]
        path = path.strip('"').replace("\\", "/").strip()
        if path:
            changed.append(path)

    if not changed:
        return {"committed": False, "commit": None, "pushed": False,
                "error": "Keine Aenderungen vorhanden; kein Commit noetig."}

    # 3. Whitelist-Pruefung: kein 'git add', wenn unerwartete Dateien da sind.
    whitelist = expected_git_files(kind, task_id, run_id)
    unexpected = sorted(p for p in changed if not matches_whitelist(p, whitelist))
    if unexpected:
        return {"committed": False, "commit": None, "pushed": False,
                "error": (
                    "Whitelist-Pruefung fehlgeschlagen — unerwartete Aenderungen: "
                    + ", ".join(unexpected)
                    + ". Kein git add ausgefuehrt, Commit abgebrochen."
                )}

    # 4. git add — ausschliesslich die konkret geaenderten Whitelisted-Dateien.
    #    KEIN 'git add -A', KEIN 'git add .'.
    r = _run(["git", "add", "--"] + changed)
    if r.returncode != 0:
        return {"committed": False, "commit": None, "pushed": False,
                "error": f"git add fehlgeschlagen: {r.stderr.strip()}"}

    # 5. git commit.
    msg = f"Ops: {task_id} {kind} (Steuerchat-Aktion via {source})"
    r = _run(["git", "commit", "-m", msg])
    if r.returncode != 0:
        return {"committed": False, "commit": None, "pushed": False,
                "error": f"git commit fehlgeschlagen: {r.stderr.strip()}"}

    r_sha = _run(["git", "rev-parse", "--short", "HEAD"])
    commit_sha = r_sha.stdout.strip() if r_sha.returncode == 0 else None

    if not push:
        return {"committed": True, "commit": commit_sha, "pushed": False,
                "error": None}

    # 6. git push — Force-Push ist kategorisch verboten (nie force/force-with-lease).
    r = _run(["git", "push"], timeout=_GIT_PUSH_TIMEOUT)
    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip()
        return {"committed": True, "commit": commit_sha, "pushed": False,
                "error": f"git push fehlgeschlagen: {err}"}

    return {"committed": True, "commit": commit_sha, "pushed": True, "error": None}
