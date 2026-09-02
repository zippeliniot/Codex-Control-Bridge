"""Hermetische Tests für die Ablage-Schicht (BRIDGE-005). stdlib unittest."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from bridge import state_machine  # noqa: E402
from bridge.store import (  # noqa: E402
    Store,
    StoreError,
    SchemaValidationError,
    _FORMAT_CHECKER,
)

SCHEMA_DIR = REPO_ROOT / "schemas"
TS = "2026-01-01T00:00:00Z"


def valid_task(**over):
    doc = {
        "schema_version": "1.0",
        "kind": "bridge_task",
        "bridge_task_id": "BRIDGE-900",
        "project_id": "codex-control-bridge",
        "title": "Testauftrag",
        "description": "Nur für Tests.",
        "task_class": "FEATURE",
        "repository": "Codex-Control-Bridge",
        "branch": "main",
        "permissions": ["READ_ONLY"],
        "status": "CREATED",
        "created_at": TS,
        "created_by": "steuerprozess",
    }
    doc.update(over)
    return doc


def valid_result(**over):
    doc = {
        "schema_version": "1.0",
        "kind": "bridge_result",
        "bridge_task_id": "BRIDGE-900",
        "project_id": "codex-control-bridge",
        "run_id": "RUN-01",
        "status": "COMPLETED",
        "repository": "Codex-Control-Bridge",
        "branch": "main",
        "head": "0" * 40,
        "executor": "claude-code",
        "started_at": TS,
        "ended_at": TS,
        "created_by": "claude-code",
    }
    doc.update(over)
    return doc


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-store-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()
        self.store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def audit_events(self):
        f = self.tmp / "audit" / "audit.jsonl"
        if not f.exists():
            return []
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]

    def event_types(self):
        return [e["event_type"] for e in self.audit_events()]

    # -- create_task ---------------------------------------------------

    def test_valid_task_writes_file_and_audit(self):
        self.store.create_task(valid_task())
        path = self.tmp / "tasks" / "BRIDGE-900" / "task.yaml"
        self.assertTrue(path.exists())
        self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8"))["status"], "CREATED")
        self.assertEqual(self.event_types(), ["TASK_CREATED"])

    def test_invalid_task_missing_field_rejected(self):
        bad = valid_task()
        del bad["title"]
        with self.assertRaises(SchemaValidationError):
            self.store.create_task(bad)
        self.assertFalse((self.tmp / "tasks" / "BRIDGE-900").exists())
        self.assertEqual(self.audit_events(), [])

    def test_invalid_task_unknown_field_rejected(self):
        with self.assertRaises(SchemaValidationError):
            self.store.create_task(valid_task(unerwartetes_feld="x"))
        self.assertEqual(self.audit_events(), [])

    def test_create_task_twice_rejected(self):
        self.store.create_task(valid_task())
        with self.assertRaises(StoreError):
            self.store.create_task(valid_task())
        self.assertEqual(self.event_types(), ["TASK_CREATED"])

    # -- set_status --------------------------------------------------

    def test_allowed_transition(self):
        self.store.create_task(valid_task())
        self.store.set_status("BRIDGE-900", "READY", actor="steuerprozess")
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "READY")
        self.assertEqual(self.event_types(), ["TASK_CREATED", "TASK_READY"])

    def test_disallowed_transition_no_side_effects(self):
        self.store.create_task(valid_task())
        with self.assertRaises(state_machine.TransitionError):
            self.store.set_status("BRIDGE-900", "RUNNING", actor="x")
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "CREATED")
        self.assertEqual(self.event_types(), ["TASK_CREATED"])

    def test_resume_special_case(self):
        self.store.create_task(valid_task())
        for state in ("READY", "CLAIMED", "RUNNING", "INTERRUPTED", "WAITING_FOR_RESUME"):
            self.store.set_status("BRIDGE-900", state, actor="x")
        ev = self.store.set_status("BRIDGE-900", "RUNNING", actor="x")
        self.assertEqual(ev["event_type"], "TASK_RESUMED")
        self.assertEqual(self.event_types()[-1], "TASK_RESUMED")

    # -- runs / results --------------------------------------------

    def test_next_run_id(self):
        self.store.create_task(valid_task())
        self.assertEqual(self.store.next_run_id("BRIDGE-900"), "RUN-01")
        self.store.write_result(valid_result(run_id="RUN-01"))
        self.assertEqual(self.store.next_run_id("BRIDGE-900"), "RUN-02")

    def test_write_result_writes_file_and_audit(self):
        self.store.create_task(valid_task())
        self.store.write_result(valid_result())
        self.assertTrue((self.tmp / "results" / "BRIDGE-900" / "RUN-01" / "result.yaml").exists())
        self.assertEqual(self.event_types(), ["TASK_CREATED", "RESULT_WRITTEN"])

    def test_result_without_task_rejected(self):
        with self.assertRaises(StoreError):
            self.store.write_result(valid_result(bridge_task_id="BRIDGE-901"))

    def test_result_existing_run_rejected(self):
        self.store.create_task(valid_task())
        self.store.write_result(valid_result())
        with self.assertRaises(StoreError):
            self.store.write_result(valid_result())

    # -- audit / pfade ---------------------------------------------

    def test_audit_append_only_and_schema_conform(self):
        self.store.create_task(valid_task())
        self.store.set_status("BRIDGE-900", "READY", actor="x")
        first = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.store.set_status("BRIDGE-900", "CLAIMED", actor="x")
        second = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertTrue(second.startswith(first))
        schema = yaml.safe_load((SCHEMA_DIR / "audit-event.schema.yaml").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)
        for event in self.audit_events():
            validator.validate(event)

    def test_path_escaping_rejected(self):
        with self.assertRaises(StoreError):
            self.store.load_task("../../evil")
        with self.assertRaises(StoreError):
            self.store.next_run_id("BRIDGE-900/../../evil")


if __name__ == "__main__":
    unittest.main()
