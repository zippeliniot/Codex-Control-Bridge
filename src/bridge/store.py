"""Ablage & Validierung der Codex Control Bridge (BRIDGE-005).

Kapselt das Ablage-Layout aus docs/protocols/storage-layout.md: Aufträge unter
``tasks/``, Ergebnisse unter ``results/``, die append-only Auditspur unter
``audit/audit.jsonl``.

Alle Pfade sind über ``Store(root=..., schema_dir=...)`` parametrierbar, damit
Tests hermetisch in einem Temp-Verzeichnis laufen. Fail-closed: unbekannter
Zustand, unerlaubter Übergang, Schemafehler, fehlender Auftrag, bereits
existierende Zieldatei oder ein Pfad außerhalb ``root`` führen zu einer
Exception - es wird nichts geschrieben.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# src-Layout: bei direktem Skriptaufruf (python src/bridge/store.py ...) muss
# das Paketverzeichnis auf den Importpfad, sonst schlägt 'from bridge import ...' fehl.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from bridge import state_machine


class StoreError(Exception):
    """Basisfehler der Ablage-Schicht (fail-closed)."""


class SchemaValidationError(StoreError):
    """Ein Dokument verletzt sein Schema."""


# --- date-time-Prüfung (RFC 3339), deterministisch, ohne Zusatzabhängigkeit ---

_FORMAT_CHECKER = FormatChecker()

_RFC3339_RE = re.compile(
    r"^(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})"
    r"[Tt](?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})(?:\.\d+)?"
    r"(?:[Zz]|[+-]\d{2}:\d{2})$"
)


@_FORMAT_CHECKER.checks("date-time")
def _is_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    m = _RFC3339_RE.match(value)
    if not m:
        return False
    try:
        datetime(int(m["y"]), int(m["mo"]), int(m["d"]),
                 int(m["h"]), int(m["mi"]), int(m["s"]))
    except ValueError:
        return False
    return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_ID_RE = re.compile(r"^BRIDGE-[0-9]{3,}$")
_RUN_RE = re.compile(r"^RUN-[0-9]{2,}$")
_KIND_TO_SCHEMA = {
    "bridge_task": "task.schema.yaml",
    "bridge_result": "result.schema.yaml",
}


def _load_yaml(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"Datei nicht lesbar: {path} ({exc})") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StoreError(f"Kein gültiges YAML: {path} ({exc})") from exc


class Store:
    def __init__(self, root, schema_dir=None):
        self.root = Path(root).resolve()
        self.schema_dir = (
            Path(schema_dir).resolve() if schema_dir is not None
            else self.root / "schemas"
        )
        self.tasks_dir = self.root / "tasks"
        self.results_dir = self.root / "results"
        self.audit_dir = self.root / "audit"
        self.audit_file = self.audit_dir / "audit.jsonl"

        self._validators = {}
        model = state_machine.load_model(self.schema_dir / "state-model.yaml")
        self.initial_state = model["initial_state"]
        self._event_map = self._load_event_map()

    # ----- interne Helfer ---------------------------------------------------

    def _load_event_map(self) -> dict:
        data = _load_yaml(self.schema_dir / "audit-event-map.yaml")
        if not isinstance(data, dict) or "by_new_state" not in data:
            raise StoreError("audit-event-map.yaml unbrauchbar.")
        data.setdefault("from_state_override", {})
        return data

    def _validator(self, schema_name: str) -> Draft202012Validator:
        if schema_name not in self._validators:
            schema = _load_yaml(self.schema_dir / schema_name)
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise StoreError(f"Schema fehlerhaft: {schema_name} ({exc})") from exc
            self._validators[schema_name] = Draft202012Validator(
                schema, format_checker=_FORMAT_CHECKER
            )
        return self._validators[schema_name]

    def _validate_against(self, doc: dict, schema_name: str, label: str) -> None:
        validator = self._validator(schema_name)
        errors = sorted(validator.iter_errors(doc), key=lambda e: str(list(e.path)))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.path) or "(Wurzel)"
            raise SchemaValidationError(
                f"{label} ungültig: {first.message} [Feld: {where}]"
            )

    def _check_id(self, task_id) -> str:
        if not isinstance(task_id, str) or not _ID_RE.match(task_id):
            raise StoreError(f"Unzulässige bridge_task_id: {task_id!r}")
        return task_id

    def _in_root(self, path) -> Path:
        resolved = Path(path).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise StoreError(f"Pfad außerhalb root: {resolved}")
        return resolved

    def _write_new(self, path, text: str) -> None:
        target = self._in_root(path)
        if target.exists():
            raise StoreError(f"Ziel existiert bereits (kein Überschreiben): {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    @staticmethod
    def _as_doc(doc_or_path):
        if isinstance(doc_or_path, (str, Path)):
            return _load_yaml(Path(doc_or_path))
        return doc_or_path

    @staticmethod
    def _dump_yaml(doc: dict) -> str:
        return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / self._check_id(task_id) / "task.yaml"

    # ----- öffentliche API ------------------------------------------------

    def validate(self, doc_or_path):
        doc = self._as_doc(doc_or_path)
        if not isinstance(doc, dict):
            raise SchemaValidationError("Dokument ist kein Objekt.")
        schema_name = _KIND_TO_SCHEMA.get(doc.get("kind"))
        if schema_name is None:
            raise SchemaValidationError(
                f"Unbekanntes oder fehlendes 'kind': {doc.get('kind')!r}"
            )
        self._validate_against(doc, schema_name, doc["kind"])
        return doc

    def create_task(self, task):
        doc = self.validate(self._as_doc(task))
        if doc["kind"] != "bridge_task":
            raise SchemaValidationError("create_task erwartet kind=bridge_task.")
        task_id = self._check_id(doc["bridge_task_id"])
        path = self._task_path(task_id)
        if self._in_root(path).exists():
            raise StoreError(f"Auftrag existiert bereits: {task_id}")
        doc = dict(doc)
        doc["status"] = self.initial_state
        self._write_new(path, self._dump_yaml(doc))
        self.append_audit(self._event(
            "TASK_CREATED", task_id,
            actor=doc.get("created_by", "unknown"),
            new_state=self.initial_state,
        ))
        return doc

    def load_task(self, task_id):
        path = self._in_root(self._task_path(task_id))
        if not path.exists():
            raise StoreError(f"Auftrag nicht gefunden: {task_id}")
        doc = _load_yaml(path)
        if not isinstance(doc, dict):
            raise StoreError(f"Auftragsdatei unbrauchbar: {path}")
        return doc

    def save_task(self, task):
        doc = self.validate(self._as_doc(task))
        path = self._in_root(self._task_path(doc["bridge_task_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._dump_yaml(doc), encoding="utf-8")
        return doc

    def _event_type_for(self, from_state: str, to_state: str) -> str:
        override = self._event_map.get("from_state_override", {})
        if from_state in override:
            return override[from_state]
        by_new = self._event_map["by_new_state"]
        if to_state not in by_new:
            raise StoreError(
                f"Kein event_type für Zielzustand {to_state} in audit-event-map.yaml"
            )
        return by_new[to_state]

    def set_status(self, task_id, new_state, actor, machine=None, reason=None):
        task_id = self._check_id(task_id)
        task = self.load_task(task_id)
        old_state = task.get("status")
        # Fail-closed VOR jedem Schreiben.
        state_machine.assert_transition(old_state, new_state)
        event = self._event(
            self._event_type_for(old_state, new_state), task_id,
            actor=actor, machine=machine,
            old_state=old_state, new_state=new_state, reason=reason,
        )
        self._validate_audit(event)
        task["status"] = new_state
        self.save_task(task)
        self.append_audit(event)
        return event

    def next_run_id(self, task_id):
        task_id = self._check_id(task_id)
        run_dir = self._in_root(self.results_dir / task_id)
        highest = 0
        if run_dir.exists():
            for entry in run_dir.iterdir():
                if entry.is_dir() and _RUN_RE.match(entry.name):
                    highest = max(highest, int(entry.name.split("-")[1]))
        return f"RUN-{highest + 1:02d}"

    def write_result(self, result):
        doc = self.validate(self._as_doc(result))
        if doc["kind"] != "bridge_result":
            raise SchemaValidationError("write_result erwartet kind=bridge_result.")
        task_id = self._check_id(doc["bridge_task_id"])
        run_id = doc["run_id"]
        if not _RUN_RE.match(run_id):
            raise StoreError(f"Unzulässige run_id: {run_id!r}")
        if not self._in_root(self._task_path(task_id)).exists():
            raise StoreError(f"Ergebnis ohne Auftrag: {task_id}")
        path = self.results_dir / task_id / run_id / "result.yaml"
        self._write_new(path, self._dump_yaml(doc))
        self.append_audit(self._event(
            "RESULT_WRITTEN", task_id,
            actor=doc.get("created_by", "unknown"), run_id=run_id,
        ))
        return doc

    # ----- Audit --------------------------------------------------------

    @staticmethod
    def _event(event_type, task_id, *, actor, machine=None, run_id=None,
               old_state=None, new_state=None, reason=None):
        event = {
            "event_type": event_type,
            "timestamp": _utc_now(),
            "actor": actor,
            "bridge_task_id": task_id,
        }
        for key, val in (("machine", machine), ("run_id", run_id),
                         ("old_state", old_state), ("new_state", new_state),
                         ("reason", reason)):
            if val is not None:
                event[key] = val
        return event

    def _validate_audit(self, event) -> None:
        if not isinstance(event, dict):
            raise SchemaValidationError("Audit-Ereignis ist kein Objekt.")
        self._validate_against(event, "audit-event.schema.yaml", "Audit-Ereignis")

    def append_audit(self, event):
        self._validate_audit(event)
        target = self._in_root(self.audit_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event


# --------------------------------------------------------------------------- #
# Minimale CLI
# --------------------------------------------------------------------------- #

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="store", description="Bridge-Ablage (BRIDGE-005)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").add_argument("path")
    sub.add_parser("create-task").add_argument("path")
    sp = sub.add_parser("set-status")
    sp.add_argument("task_id")
    sp.add_argument("new_state")
    sp.add_argument("--actor", required=True)
    sp.add_argument("--machine")
    sp.add_argument("--reason")
    sub.add_parser("write-result").add_argument("path")
    sub.add_parser("next-run").add_argument("task_id")
    sub.add_parser("show").add_argument("task_id")
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    store = Store(root=Path(__file__).resolve().parents[2])
    try:
        if args.cmd == "validate":
            print(f"VALID: {store.validate(args.path)['kind']}")
        elif args.cmd == "create-task":
            doc = store.create_task(args.path)
            print(f"CREATED {doc['bridge_task_id']} status={doc['status']}")
        elif args.cmd == "set-status":
            ev = store.set_status(args.task_id, args.new_state, actor=args.actor,
                                  machine=args.machine, reason=args.reason)
            print(f"{ev['old_state']} -> {ev['new_state']} ({ev['event_type']})")
        elif args.cmd == "write-result":
            doc = store.write_result(args.path)
            print(f"RESULT {doc['bridge_task_id']} {doc['run_id']}")
        elif args.cmd == "next-run":
            print(store.next_run_id(args.task_id))
        elif args.cmd == "show":
            print(store.load_task(args.task_id).get("status"))
    except (StoreError, state_machine.TransitionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
