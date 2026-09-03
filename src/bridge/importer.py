"""Result-Importer der Codex Control Bridge (BRIDGE-007).

Übernimmt ein Ergebnis aus dem tatsächlichen Executor-Kontext strukturiert und
legt es als valides ``result.yaml`` ab - statt es von Hand zu schreiben.

Die *objektiven* Felder (Git-Provenienz, Umgebung, Zeit) ermittelt der Importer
automatisch; die *subjektiven* (summary, acceptance_results, Unterbrechung)
kommen aus einem Entwurf (YAML-dict) und/oder expliziten Argumenten - das
Argument gewinnt.

Fail-closed: fehlender Auftrag, Schemafehler, bereits existierender Lauf oder
ein Git-Fehler führen zu einer Exception; es wird nichts geschrieben. Der
Git-Zugriff ist über ``git_info_fn`` injizierbar, damit Tests hermetisch ohne
echtes Git laufen.

Nur Standardbibliothek (``subprocess`` für Git); ``yaml`` nur zum Einlesen des
Entwurfs (bereits Projektabhängigkeit über die Ablage-Schicht).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml


class ImporterError(Exception):
    """Fehler beim Ermitteln der Provenienz oder beim Einlesen des Entwurfs."""


_SUBJECTIVE = (
    "summary",
    "acceptance_results",
    "interruption_reason",
    "resumable",
    "resume_hint",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Git-Provenienz (read-only, echtes Git) - injizierbar über git_info_fn
# --------------------------------------------------------------------------- #

def _git(root, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ImporterError(f"git {' '.join(args)} nicht ausführbar: {exc}") from exc
    if proc.returncode != 0:
        raise ImporterError(
            f"git {' '.join(args)} fehlgeschlagen (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def collect_git_info(root, base_head=None) -> dict:
    """Ermittelt Repository/Branch/HEAD sowie - bei gesetztem ``base_head`` -
    die im Lauf erzeugten Commits und geänderten Dateien. Fail-closed bei jedem
    Git-Fehler (nichts erfinden)."""
    toplevel = _git(root, "rev-parse", "--show-toplevel")
    info = {
        "repository": Path(toplevel).name,
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git(root, "rev-parse", "HEAD"),
        "base_head": base_head,
        "commits": [],
        "changed_files": [],
    }
    if base_head:
        shas = _lines(_git(root, "rev-list", "--reverse", f"{base_head}..HEAD"))
        info["commits"] = [
            {"sha": sha, "message": _git(root, "log", "-1", "--format=%s", sha)}
            for sha in shas
        ]
        info["changed_files"] = _lines(
            _git(root, "diff", "--name-only", base_head, "HEAD")
        )
    else:
        info["changed_files"] = _lines(
            _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        )
    return info


# --------------------------------------------------------------------------- #
# Entwurf einlesen
# --------------------------------------------------------------------------- #

def load_draft(path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ImporterError(f"Entwurf nicht lesbar: {path} ({exc})") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ImporterError(f"Entwurf kein gültiges YAML: {path} ({exc})") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ImporterError(f"Entwurf ist kein Objekt: {path}")
    return data


# --------------------------------------------------------------------------- #
# Ergebnis bauen / importieren
# --------------------------------------------------------------------------- #

def build_result(store, bridge_task_id, status, *, run_id=None, draft=None,
                 base_head=None, executor="claude-code", machine=None,
                 environment=None, runtime=None, model=None,
                 reasoning_level=None, started_at=None, created_by=None,
                 summary=None, acceptance_results=None, interruption_reason=None,
                 resumable=None, resume_hint=None, git_info_fn=None) -> dict:
    """Setzt das Ergebnis-dict zusammen (ohne zu schreiben oder zu validieren)."""
    draft = draft or {}
    if not isinstance(draft, dict):
        raise ImporterError("draft muss ein dict sein.")

    task = store.load_task(bridge_task_id)  # fail-closed, wenn Auftrag fehlt
    project_id = task.get("project_id")
    if not project_id:
        raise ImporterError(f"Auftrag {bridge_task_id} ohne project_id.")

    rid = run_id or store.next_run_id(bridge_task_id)

    git_info_fn = git_info_fn or collect_git_info
    git = git_info_fn(store.root, base_head=base_head)

    ended_at = _utc_now()
    started = started_at if started_at is not None else draft.get("started_at")
    started = started or ended_at

    machine = machine or os.environ.get("BRIDGE_MACHINE")
    environment = environment or os.environ.get("BRIDGE_ENV")
    runtime = runtime or os.environ.get("BRIDGE_RUNTIME")

    result = {
        "schema_version": "1.0",
        "kind": "bridge_result",
        "bridge_task_id": bridge_task_id,
        "project_id": project_id,
        "run_id": rid,
        "status": status,
        "repository": git["repository"],
        "branch": git["branch"],
        "head": git["head"],
        "executor": executor,
        "started_at": started,
        "ended_at": ended_at,
        "created_by": created_by or f"{executor}@{machine or 'unknown'}",
    }

    if git.get("base_head") is not None:
        result["base_head"] = git["base_head"]
    if git.get("commits"):
        result["commits"] = git["commits"]
    if git.get("changed_files"):
        result["changed_files"] = git["changed_files"]

    explicit = {
        "summary": summary,
        "acceptance_results": acceptance_results,
        "interruption_reason": interruption_reason,
        "resumable": resumable,
        "resume_hint": resume_hint,
    }
    for key in _SUBJECTIVE:
        value = explicit[key] if explicit[key] is not None else draft.get(key)
        if value is not None:
            result[key] = value

    for key, value in (
        ("physical_machine", machine),
        ("environment", environment),
        ("runtime", runtime),
        ("model", model),
        ("reasoning_level", reasoning_level),
    ):
        if value is not None:
            result[key] = value

    return result


def import_result(store, bridge_task_id, status, **kwargs) -> dict:
    """build_result -> store.validate -> store.write_result. Fail-closed:
    Schemafehler / fehlender Auftrag / vorhandener Lauf -> Fehler, kein Schreiben."""
    result = build_result(store, bridge_task_id, status, **kwargs)
    store.validate(result)
    store.write_result(result)
    return result
