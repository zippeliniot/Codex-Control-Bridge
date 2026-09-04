"""Heartbeat-Dateien laufender Auftrags-Läufe (BRIDGE-008).

Ein lebendiger Executor aktualisiert ``results/<id>/RUN-<yy>/heartbeat.json``
regelmässig. Bleibt ``last_seen`` älter als das Policy-Timeout
(``schemas/watcher-policy.yaml``), gilt der Lauf als steckengeblieben und der
Watcher (``src/bridge/watcher.py``) kann ihn interruptieren.

Reine stdlib zzgl. ``pyyaml``/``jsonschema`` (bereits Projektabhängigkeit über
die Ablage-Schicht). Die Zeit ist über ``now`` (ein ``datetime``) injizierbar
-> Tests hermetisch. Das *automatische* periodische Schlagen übernimmt der
Runner (BRIDGE-009).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from jsonschema import Draft202012Validator

from bridge.store import StoreError, _FORMAT_CHECKER

_ID_RE = re.compile(r"^BRIDGE-[0-9]{3,}$")
_RUN_RE = re.compile(r"^RUN-[0-9]{2,}$")
_SCHEMA_NAME = "heartbeat.schema.yaml"


class HeartbeatError(StoreError):
    """Die Heartbeat-Datei ist vorhanden, aber unbrauchbar (fail-closed)."""


def fmt_rfc3339(moment: datetime) -> str:
    """UTC-Zeitstempel im Format ``YYYY-MM-DDTHH:MM:SSZ``."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rfc3339(value: str) -> datetime:
    """RFC-3339-Zeitstempel -> zeitzonenbewusstes ``datetime`` (UTC ohne Offset)."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HeartbeatError(f"Unlesbarer Zeitstempel: {value!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _check(task_id: str, run_id: str) -> None:
    if not isinstance(task_id, str) or not _ID_RE.match(task_id):
        raise HeartbeatError(f"Unzulässige bridge_task_id: {task_id!r}")
    if not isinstance(run_id, str) or not _RUN_RE.match(run_id):
        raise HeartbeatError(f"Unzulässige run_id: {run_id!r}")


def _resolve_schema_dir(root, schema_dir) -> Path:
    if schema_dir is not None:
        return Path(schema_dir).resolve()
    return Path(root).resolve() / "schemas"


def _validator(schema_dir: Path) -> Draft202012Validator:
    path = schema_dir / _SCHEMA_NAME
    try:
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HeartbeatError(f"Heartbeat-Schema nicht lesbar: {path} ({exc})") from exc
    return Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)


def heartbeat_path(root, bridge_task_id: str, run_id: str) -> Path:
    """``<root>/results/<id>/RUN-<yy>/heartbeat.json`` (ohne Seiteneffekt)."""
    _check(bridge_task_id, run_id)
    return (Path(root).resolve() / "results" / bridge_task_id / run_id
            / "heartbeat.json")


def beat(root, bridge_task_id: str, run_id: str, actor=None, machine=None, *,
         pid=None, now=None, schema_dir=None) -> dict:
    """Schreibt/aktualisiert die Heartbeat-Datei mit ``last_seen = now`` (UTC).

    Validiert das Dokument gegen ``heartbeat.schema.yaml`` VOR dem Schreiben
    (fail-closed). ``now`` ist ein ``datetime`` -> Tests injizieren die Zeit.
    """
    _check(bridge_task_id, run_id)
    moment = now if isinstance(now, datetime) else datetime.now(timezone.utc)
    doc = {
        "kind": "bridge_heartbeat",
        "bridge_task_id": bridge_task_id,
        "run_id": run_id,
        "last_seen": fmt_rfc3339(moment),
    }
    if actor is not None:
        doc["actor"] = actor
    if machine is not None:
        doc["machine"] = machine
    if pid is not None:
        doc["pid"] = pid

    validator = _validator(_resolve_schema_dir(root, schema_dir))
    errors = sorted(validator.iter_errors(doc), key=lambda e: str(list(e.path)))
    if errors:
        raise HeartbeatError(f"Heartbeat verletzt Schema: {errors[0].message}")

    path = heartbeat_path(root, bridge_task_id, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return doc


def read_heartbeat(root, bridge_task_id: str, run_id: str) -> dict | None:
    """Liest die Heartbeat-Datei. Fehlt sie -> ``None``. Ist sie kaputt -> Fehler."""
    path = heartbeat_path(root, bridge_task_id, run_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeartbeatError(f"Heartbeat unlesbar: {path} ({exc})") from exc
    if not isinstance(data, dict) or data.get("kind") != "bridge_heartbeat":
        raise HeartbeatError(f"Heartbeat unbrauchbar (kind falsch): {path}")
    if "last_seen" not in data:
        raise HeartbeatError(f"Heartbeat ohne last_seen: {path}")
    return data
