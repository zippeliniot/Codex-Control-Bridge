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
        "bridge_task_id": "BRIDGE-0900",
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
        "bridge_task_id": "BRIDGE-0900",
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
        path = self.tmp / "tasks" / "BRIDGE-0900" / "task.yaml"
        self.assertTrue(path.exists())
        self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8"))["status"], "CREATED")
        self.assertEqual(self.event_types(), ["TASK_CREATED"])

    def test_invalid_task_missing_field_rejected(self):
        bad = valid_task()
        del bad["title"]
        with self.assertRaises(SchemaValidationError):
            self.store.create_task(bad)
        self.assertFalse((self.tmp / "tasks" / "BRIDGE-0900").exists())
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
        self.store.set_status("BRIDGE-0900", "READY", actor="steuerprozess")
        self.assertEqual(self.store.load_task("BRIDGE-0900")["status"], "READY")
        self.assertEqual(self.event_types(), ["TASK_CREATED", "TASK_READY"])

    def test_disallowed_transition_no_side_effects(self):
        self.store.create_task(valid_task())
        with self.assertRaises(state_machine.TransitionError):
            self.store.set_status("BRIDGE-0900", "RUNNING", actor="x")
        self.assertEqual(self.store.load_task("BRIDGE-0900")["status"], "CREATED")
        self.assertEqual(self.event_types(), ["TASK_CREATED"])

    def test_resume_special_case(self):
        self.store.create_task(valid_task())
        for state in ("READY", "CLAIMED", "RUNNING", "INTERRUPTED", "WAITING_FOR_RESUME"):
            self.store.set_status("BRIDGE-0900", state, actor="x")
        ev = self.store.set_status("BRIDGE-0900", "RUNNING", actor="x")
        self.assertEqual(ev["event_type"], "TASK_RESUMED")
        self.assertEqual(self.event_types()[-1], "TASK_RESUMED")

    # -- runs / results --------------------------------------------

    def test_next_run_id(self):
        self.store.create_task(valid_task())
        self.assertEqual(self.store.next_run_id("BRIDGE-0900"), "RUN-01")
        self.store.write_result(valid_result(run_id="RUN-01"))
        self.assertEqual(self.store.next_run_id("BRIDGE-0900"), "RUN-02")

    def test_write_result_writes_file_and_audit(self):
        self.store.create_task(valid_task())
        self.store.write_result(valid_result())
        self.assertTrue((self.tmp / "results" / "BRIDGE-0900" / "RUN-01" / "result.yaml").exists())
        self.assertEqual(self.event_types(), ["TASK_CREATED", "RESULT_WRITTEN"])

    def test_result_without_task_rejected(self):
        with self.assertRaises(StoreError):
            self.store.write_result(valid_result(bridge_task_id="BRIDGE-0901"))

    def test_result_existing_run_rejected(self):
        self.store.create_task(valid_task())
        self.store.write_result(valid_result())
        with self.assertRaises(StoreError):
            self.store.write_result(valid_result())

    # -- audit / pfade ---------------------------------------------

    def test_audit_append_only_and_schema_conform(self):
        self.store.create_task(valid_task())
        self.store.set_status("BRIDGE-0900", "READY", actor="x")
        first = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.store.set_status("BRIDGE-0900", "CLAIMED", actor="x")
        second = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertTrue(second.startswith(first))
        schema = yaml.safe_load((SCHEMA_DIR / "audit-event.schema.yaml").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)
        for event in self.audit_events():
            validator.validate(event)

    # -- last_transition_at (BRIDGE-016) --------------------------

    def test_last_transition_at_finds_timestamp(self):
        self.store.create_task(valid_task())
        self.store.set_status("BRIDGE-0900", "READY", actor="x")
        self.store.set_status("BRIDGE-0900", "WAITING_FOR_HANDOFF_TO_EXECUTOR", actor="x")
        ts = self.store.last_transition_at(
            "BRIDGE-0900", "WAITING_FOR_HANDOFF_TO_EXECUTOR")
        match = [e for e in self.audit_events()
                 if e.get("new_state") == "WAITING_FOR_HANDOFF_TO_EXECUTOR"]
        self.assertEqual(ts, match[-1]["timestamp"])

    def test_last_transition_at_returns_last_occurrence(self):
        self.store.create_task(valid_task())
        for state in ("READY", "CLAIMED", "RUNNING", "FAILED", "READY"):
            self.store.set_status("BRIDGE-0900", state, actor="x")
        ready = [e for e in self.audit_events() if e.get("new_state") == "READY"]
        self.assertEqual(len(ready), 2)
        self.assertEqual(
            self.store.last_transition_at("BRIDGE-0900", "READY"),
            ready[-1]["timestamp"])

    def test_last_transition_at_none_without_match(self):
        self.store.create_task(valid_task())
        self.assertIsNone(self.store.last_transition_at("BRIDGE-0900", "ARCHIVED"))
        self.assertIsNone(self.store.last_transition_at("BRIDGE-9999", "READY"))

    def test_path_escaping_rejected(self):
        with self.assertRaises(StoreError):
            self.store.load_task("../../evil")
        with self.assertRaises(StoreError):
            self.store.next_run_id("BRIDGE-0900/../../evil")


class IdFormatTests(unittest.TestCase):
    """BRIDGE-015: <PRAEFIX bis 8 Grossbuchstaben>-<4 Ziffern>."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-idfmt-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()
        self.store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_non_bridge_prefix_accepted(self):
        doc = self.store.create_task(valid_task(bridge_task_id="DORF-0001"))
        self.assertEqual(doc["bridge_task_id"], "DORF-0001")
        self.assertTrue((self.tmp / "tasks" / "DORF-0001" / "task.yaml").exists())
        self.store.validate(valid_task(bridge_task_id="DORF-0001"))

    def test_three_digit_number_rejected(self):
        with self.assertRaises(StoreError):
            self.store.create_task(valid_task(bridge_task_id="BRIDGE-042"))
        self.assertFalse((self.tmp / "tasks" / "BRIDGE-042").exists())

    def test_nine_letter_prefix_rejected(self):
        with self.assertRaises(StoreError):
            self.store.create_task(valid_task(bridge_task_id="ABCDEFGHI-0001"))


if __name__ == "__main__":
    unittest.main()
