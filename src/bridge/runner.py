"""Lauf-Lebenszyklus-Orchestrierung (BRIDGE-009).

Ein Lauf wird gestartet, per Heartbeat begleitet, abgeschlossen und
wiederaufgenommen - mit den vorhandenen Bausteinen (store, importer, heartbeat,
state_machine). Der Runner ist KEIN KI-Executor; die inhaltliche Arbeit macht
weiterhin Claude Code/Codex.

Sicherheits-Leitplanken:
- Nie Git. Geschrieben werden nur task.yaml, result.yaml, Heartbeat, Auditspur.
- Nur erlaubte Übergänge, jeweils über state_machine / Store.set_status.
- Fail-closed: Auftrag im falschen Zustand / mehrdeutige Lage -> RunnerError.

Zeit (``now``, ein ``datetime``) und Git (``git_info_fn``) sind injizierbar,
damit Tests hermetisch bleiben.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from bridge import heartbeat, importer, state_machine
from bridge.store import StoreError

_RUN_RE = re.compile(r"^RUN-[0-9]{2,}$")

# Feste Startkette bis zum laufenden Zustand.
_START_CHAIN = ("CREATED", "READY", "CLAIMED", "RUNNING")
_START_FROM = _START_CHAIN[:-1]           # zulässige Ausgangszustände für start()
_RESUME_FROM = ("INTERRUPTED", "WAITING_FOR_RESUME")


class RunnerError(StoreError):
    """Der Lauf-Lebenszyklus ist im aktuellen Zustand nicht durchführbar (fail-closed)."""


# --------------------------------------------------------------------------- #
# Lese-Helfer (rein lesend, nie Git)
# --------------------------------------------------------------------------- #

def _runs(store, task_id):
    run_dir = store.results_dir / task_id
    if not run_dir.exists():
        return []
    return sorted(
        (e.name for e in run_dir.iterdir()
         if e.is_dir() and _RUN_RE.match(e.name)),
        key=lambda r: int(r.split("-")[1]),
    )


def current_run_id(store, task_id):
    """Höchstes vorhandenes ``results/<id>/RUN-*`` oder ``None``."""
    runs = _runs(store, task_id)
    return runs[-1] if runs else None


def open_acceptance_criteria(store, task_id) -> list[str]:
    """Offene ``- [ ]``-Haken aus ``work-packages/<id>.md`` (falls vorhanden)."""
    wp = store.root / "work-packages" / f"{task_id}.md"
    if not wp.is_file():
        return []
    out = []
    for raw in wp.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("- [ ]"):
            out.append(stripped[5:].strip())
    return out


def last_result(store, task_id) -> dict | None:
    """Jüngstes ``result.yaml`` über alle Läufe oder ``None``."""
    for run_id in reversed(_runs(store, task_id)):
        path = store.results_dir / task_id / run_id / "result.yaml"
        if path.exists():
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return doc
    return None


def last_resume_hint(store, task_id) -> str | None:
    doc = last_result(store, task_id)
    return doc.get("resume_hint") if doc else None


# --------------------------------------------------------------------------- #
# Lebenszyklus
# --------------------------------------------------------------------------- #

def start(store, task_id, actor, machine=None, *, now=None) -> str:
    """CREATED/READY/CLAIMED -> RUNNING (nur fehlende Schritte), initialer Heartbeat."""
    status = store.load_task(task_id).get("status")
    if status not in _START_FROM:
        raise RunnerError(
            f"start nur aus {'/'.join(_START_FROM)} zulässig (Auftrag ist {status}).")
    for nxt in _START_CHAIN[_START_CHAIN.index(status) + 1:]:
        store.set_status(task_id, nxt, actor, machine, reason=f"runner: start -> {nxt}")
    run_id = store.next_run_id(task_id)
    heartbeat.beat(store.root, task_id, run_id, actor=actor, machine=machine,
                   now=now, schema_dir=store.schema_dir)
    return run_id


def beat(store, task_id, actor=None, machine=None, *, now=None) -> dict:
    """Heartbeat des aktuellen Laufs aktualisieren (nur im Status RUNNING)."""
    status = store.load_task(task_id).get("status")
    if status != "RUNNING":
        raise RunnerError(f"beat nur im Status RUNNING (Auftrag ist {status}).")
    run_id = current_run_id(store, task_id)
    if run_id is None:
        raise RunnerError("beat: kein laufender RUN vorhanden.")
    return heartbeat.beat(store.root, task_id, run_id, actor=actor, machine=machine,
                          now=now, schema_dir=store.schema_dir)


def finish(store, task_id, status, *, draft=None, base_head=None, actor,
           machine=None, git_info_fn=None, now=None, **prov):
    """Ein Schritt: Übergang prüfen -> Ergebnis importieren -> Status setzen.

    Bei nicht erlaubtem Übergang RUNNING->status wird NICHTS geschrieben.
    """
    current = store.load_task(task_id).get("status")
    if current != "RUNNING":
        raise RunnerError(f"finish nur aus RUNNING zulässig (Auftrag ist {current}).")
    if not state_machine.is_allowed("RUNNING", status):
        raise RunnerError(f"Übergang RUNNING -> {status} nicht erlaubt (fail-closed).")
    run_id = current_run_id(store, task_id)
    if run_id is None:
        raise RunnerError("finish: kein laufender RUN vorhanden.")

    draft = draft or {}
    prov = dict(prov)
    if not prov.get("started_at") and not draft.get("started_at"):
        hb = heartbeat.read_heartbeat(store.root, task_id, run_id)
        if hb:
            prov["started_at"] = hb["last_seen"]
        elif now is not None:
            prov["started_at"] = heartbeat.fmt_rfc3339(now)

    result = importer.import_result(
        store, task_id, status,
        run_id=run_id, draft=draft, base_head=base_head,
        machine=machine, git_info_fn=git_info_fn, **prov,
    )
    event = store.set_status(task_id, status, actor, machine,
                             reason=f"runner: finish -> {status}")
    return result, event


def resume(store, task_id, actor, machine=None, *, now=None) -> str:
    """INTERRUPTED/WAITING_FOR_RESUME -> RUNNING (ein Schritt), neuer RUN, frischer Heartbeat."""
    status = store.load_task(task_id).get("status")
    if status not in _RESUME_FROM:
        raise RunnerError(
            f"resume nur aus {'/'.join(_RESUME_FROM)} zulässig (Auftrag ist {status}).")
    if status == "INTERRUPTED":
        store.set_status(task_id, "WAITING_FOR_RESUME", actor, machine,
                         reason="runner: resume")
    store.set_status(task_id, "RUNNING", actor, machine, reason="runner: resume")
    run_id = store.next_run_id(task_id)
    heartbeat.beat(store.root, task_id, run_id, actor=actor, machine=machine,
                   now=now, schema_dir=store.schema_dir)
    return run_id
