"""Watcher: erkennt fertige Ergebnisse und tote Heartbeats (BRIDGE-008).

Der Watcher liest den Repo-Zustand und die Policy
(``schemas/watcher-policy.yaml``) und führt Aufträge automatisch weiter -
aber nur mit ``apply=True``, nur über von der Policy erlaubte Übergänge, jeder
zusätzlich durch den BRIDGE-004-Validator geprüft, und NIEMALS mit Git-Aktionen.
Bei totem Heartbeat wird ausschliesslich der Auftragsstatus (+ Audit-Reason)
gesetzt - es wird KEIN ``result.yaml`` erfunden.

Fail-closed: mehrdeutige Lage, kaputter Heartbeat, nicht erlaubter Übergang
-> nichts tun, melden. Die Zeit ist über ``now`` injizierbar.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from bridge import heartbeat, state_machine
from bridge.store import StoreError

_RUN_RE = re.compile(r"^RUN-[0-9]{2,}$")
_RUNNING_EVENTS = ("TASK_STARTED", "TASK_RESUMED")


class WatcherError(StoreError):
    """Policy fehlt/ist unbrauchbar oder der Repo-Zustand ist mehrdeutig."""


@dataclass
class Finding:
    kind: str                 # "result" | "stale"
    bridge_task_id: str
    run_id: str
    from_status: str
    target: str
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        """True nur, wenn der Zielübergang laut state-model erlaubt ist."""
        return state_machine.is_allowed(self.from_status, self.target)


@dataclass
class Applied:
    finding: Finding
    applied: bool
    detail: str


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #

def load_policy(schema_dir) -> dict:
    path = Path(schema_dir) / "watcher-policy.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WatcherError(f"Policy nicht lesbar: {path} ({exc})") from exc
    except yaml.YAMLError as exc:
        raise WatcherError(f"Policy kein gültiges YAML: {path} ({exc})") from exc
    if not isinstance(data, dict) or data.get("kind") != "bridge_watcher_policy":
        raise WatcherError(f"Policy unbrauchbar (kind falsch): {path}")
    for key in ("heartbeat_timeout_seconds", "eligible_from_status",
                "on_result_status", "on_stale_heartbeat"):
        if key not in data:
            raise WatcherError(f"Policy: Pflichtfeld fehlt: {key}")
    if "to_status" not in (data["on_stale_heartbeat"] or {}):
        raise WatcherError("Policy: on_stale_heartbeat.to_status fehlt")
    return data


# --------------------------------------------------------------------------- #
# Repo-Zustand lesen (rein lesend, nie Git)
# --------------------------------------------------------------------------- #

def _iter_tasks(store):
    if not store.tasks_dir.exists():
        return
    for entry in sorted(store.tasks_dir.iterdir()):
        if not (entry / "task.yaml").is_file():
            continue
        try:
            task = store.load_task(entry.name)
        except StoreError:
            continue
        yield task.get("bridge_task_id", entry.name), task.get("status")


def _last_run(store, task_id):
    run_dir = store.results_dir / task_id
    runs = []
    if run_dir.exists():
        for entry in run_dir.iterdir():
            if entry.is_dir() and _RUN_RE.match(entry.name):
                runs.append(entry.name)
    return max(runs, key=lambda r: int(r.split("-")[1])) if runs else None


def _read_result(store, task_id, run_id):
    path = store.results_dir / task_id / run_id / "result.yaml"
    if not path.exists():
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WatcherError(f"result.yaml unlesbar: {path} ({exc})") from exc
    if not isinstance(doc, dict):
        raise WatcherError(f"result.yaml unbrauchbar: {path}")
    return doc


def _audit_events(store, task_id):
    path = store.audit_file
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("bridge_task_id") == task_id:
            events.append(event)
    return events


def _run_started_at(store, task_id):
    """Zeitpunkt des jüngsten Laufbeginns (TASK_STARTED/TASK_RESUMED) oder None."""
    for event in reversed(_audit_events(store, task_id)):
        if event.get("event_type") in _RUNNING_EVENTS and event.get("timestamp"):
            return heartbeat.parse_rfc3339(event["timestamp"])
    return None


# --------------------------------------------------------------------------- #
# scan / apply / run_once / loop
# --------------------------------------------------------------------------- #

def scan(store, policy, *, now=None) -> list[Finding]:
    now = now if isinstance(now, datetime) else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    timeout = float(policy["heartbeat_timeout_seconds"])
    eligible = set(policy["eligible_from_status"])
    on_result = policy.get("on_result_status") or {}
    stale_target = policy["on_stale_heartbeat"]["to_status"]
    stale_reason = policy["on_stale_heartbeat"].get(
        "audit_reason", "watcher: heartbeat älter als timeout")

    findings: list[Finding] = []
    for task_id, status in _iter_tasks(store):
        if status not in eligible:
            continue
        run_id = _last_run(store, task_id)
        if run_id is None:
            continue  # kein Lauf -> nichts zu tun (fail-closed)

        # (1) Ergebnis fertig? -> hat Vorrang vor stale.
        result = _read_result(store, task_id, run_id)
        if result is not None:
            target = on_result.get(result.get("status"))
            if target:
                findings.append(Finding(
                    "result", task_id, run_id, status, target,
                    reason=f"watcher: Ergebnis {result.get('status')} erkannt",
                ))
            continue

        # (2) Heartbeat tot? (kaputte Datei -> HeartbeatError = fail-closed)
        hb = heartbeat.read_heartbeat(store.root, task_id, run_id)
        if hb is not None:
            last_seen = heartbeat.parse_rfc3339(hb["last_seen"])
            reason = stale_reason
        else:
            last_seen = _run_started_at(store, task_id)
            if last_seen is None:
                continue  # mehrdeutig -> fail-closed
            reason = f"{stale_reason} (kein Heartbeat seit Laufbeginn)"

        if (now - last_seen).total_seconds() > timeout:
            findings.append(Finding(
                "stale", task_id, run_id, status, stale_target, reason=reason))
    return findings


def apply(store, findings, actor, machine=None) -> list[Applied]:
    if not actor:
        raise WatcherError(
            "apply erfordert einen actor (wer verantwortet den Wechsel).")
    applied: list[Applied] = []
    for finding in findings:
        if not finding.allowed:
            applied.append(Applied(
                finding, False,
                f"übersprungen: Übergang {finding.from_status} -> "
                f"{finding.target} nicht erlaubt (fail-closed)"))
            continue
        try:
            store.set_status(finding.bridge_task_id, finding.target, actor,
                             machine, reason=finding.reason)
        except (StoreError, state_machine.TransitionError) as exc:
            applied.append(Applied(finding, False, f"übersprungen: {exc}"))
            continue
        applied.append(Applied(
            finding, True, f"{finding.from_status} -> {finding.target}"))
    return applied


_apply_findings = apply  # stabiler Name, unabhängig vom Keyword-Argument 'apply'


def run_once(store, policy, *, apply=False, actor=None, machine=None, now=None):
    findings = scan(store, policy, now=now)
    applied: list[Applied] = []
    if apply:
        applied = _apply_findings(store, findings, actor, machine)
    return findings, applied


def loop(store, policy, *, interval, apply=False, actor=None, machine=None,
         max_iterations=None, now=None, sleep=time.sleep):
    """Ruft ``run_once`` wiederholt. ``max_iterations`` und ``sleep`` sind nur
    für Tests gedacht (kein echtes Warten); ohne ``max_iterations`` endlos."""
    runs = []
    count = 0
    while max_iterations is None or count < max_iterations:
        current = now() if callable(now) else now
        runs.append(run_once(store, policy, apply=apply, actor=actor,
                             machine=machine, now=current))
        count += 1
        if max_iterations is not None and count >= max_iterations:
            break
        sleep(interval)
    return runs
