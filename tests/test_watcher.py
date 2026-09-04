"""Hermetische Tests für Heartbeat + Watcher (BRIDGE-008). stdlib unittest.

Die Zeit wird als datetime injiziert (Parameter now) - kein echtes Warten,
kein echtes Sleep, kein echtes Git.
"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bridge import heartbeat, watcher  # noqa: E402
from bridge.cli import main  # noqa: E402
from bridge.store import Store  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"
TS = "2026-01-01T00:00:00Z"
T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def valid_task(**over):
    doc = {
        "schema_version": "1.0", "kind": "bridge_task",
        "bridge_task_id": "BRIDGE-900", "project_id": "codex-control-bridge",
        "title": "Testauftrag", "description": "Nur für Tests.",
        "task_class": "FEATURE", "repository": "Codex-Control-Bridge",
        "branch": "main", "permissions": ["READ_ONLY"], "status": "CREATED",
        "created_at": TS, "created_by": "steuerprozess",
    }
    doc.update(over)
    return doc


def valid_result(**over):
    doc = {
        "schema_version": "1.0", "kind": "bridge_result",
        "bridge_task_id": "BRIDGE-900", "project_id": "codex-control-bridge",
        "run_id": "RUN-01", "status": "COMPLETED",
        "repository": "Codex-Control-Bridge", "branch": "main", "head": "0" * 40,
        "executor": "claude-code", "started_at": TS, "ended_at": TS,
        "created_by": "claude-code",
    }
    doc.update(over)
    return doc


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-watcher-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()
        self.store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        self.policy = watcher.load_policy(SCHEMA_DIR)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def running_task(self, task_id="BRIDGE-900"):
        self.store.create_task(valid_task(bridge_task_id=task_id))
        for state in ("READY", "CLAIMED", "RUNNING"):
            self.store.set_status(task_id, state, actor="steuerprozess")

    def audit_lines(self, task_id="BRIDGE-900"):
        f = self.tmp / "audit" / "audit.jsonl"
        out = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ev = json.loads(line)
                if ev.get("bridge_task_id") == task_id:
                    out.append(ev)
        return out

    def audit_types(self, task_id="BRIDGE-900"):
        return [e["event_type"] for e in self.audit_lines(task_id)]


class HeartbeatTests(Base):
    def test_beat_writes_schema_conform_and_read_back(self):
        doc = heartbeat.beat(self.tmp, "BRIDGE-900", "RUN-01",
                             actor="codex", machine="DES11",
                             now=T0, schema_dir=SCHEMA_DIR)
        self.assertEqual(doc["kind"], "bridge_heartbeat")
        self.assertEqual(doc["last_seen"], "2026-01-01T00:00:00Z")
        self.assertTrue(
            heartbeat.heartbeat_path(self.tmp, "BRIDGE-900", "RUN-01").exists())
        self.assertEqual(
            heartbeat.read_heartbeat(self.tmp, "BRIDGE-900", "RUN-01"), doc)

    def test_read_missing_returns_none(self):
        self.assertIsNone(
            heartbeat.read_heartbeat(self.tmp, "BRIDGE-900", "RUN-01"))

    def test_beat_updates_last_seen(self):
        heartbeat.beat(self.tmp, "BRIDGE-900", "RUN-01",
                       now=T0, schema_dir=SCHEMA_DIR)
        later = heartbeat.beat(self.tmp, "BRIDGE-900", "RUN-01",
                               now=T0 + timedelta(minutes=5), schema_dir=SCHEMA_DIR)
        self.assertEqual(later["last_seen"], "2026-01-01T00:05:00Z")

    def test_broken_heartbeat_file_raises(self):
        p = heartbeat.heartbeat_path(self.tmp, "BRIDGE-900", "RUN-01")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ kaputt ", encoding="utf-8")
        with self.assertRaises(heartbeat.HeartbeatError):
            heartbeat.read_heartbeat(self.tmp, "BRIDGE-900", "RUN-01")


class ScanResultTests(Base):
    def test_completed_result_scan_then_apply(self):
        self.running_task()
        self.store.write_result(valid_result())
        findings = watcher.scan(self.store, self.policy, now=T0)
        self.assertEqual([(f.kind, f.target) for f in findings],
                         [("result", "COMPLETED")])
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")

        applied = watcher.apply(self.store, findings,
                                actor="watcher", machine="DES11")
        self.assertTrue(applied[0].applied)
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "COMPLETED")
        self.assertIn("TASK_COMPLETED", self.audit_types())

    def test_dry_run_writes_nothing(self):
        self.running_task()
        self.store.write_result(valid_result())
        before = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        findings, applied = watcher.run_once(self.store, self.policy, now=T0)
        self.assertEqual(applied, [])
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")
        self.assertEqual(
            (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8"), before)

    def test_non_eligible_status_ignored(self):
        self.store.create_task(valid_task())
        self.store.set_status("BRIDGE-900", "READY", actor="x")
        self.assertEqual(watcher.scan(self.store, self.policy, now=T0), [])

    def test_disallowed_target_skipped_nothing_written(self):
        self.running_task()
        self.store.write_result(valid_result())
        bad = dict(self.policy)
        bad["on_result_status"] = dict(self.policy["on_result_status"],
                                       COMPLETED="READY")  # RUNNING->READY verboten
        findings = watcher.scan(self.store, bad, now=T0)
        self.assertEqual(len(findings), 1)
        self.assertFalse(findings[0].allowed)
        before = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        applied = watcher.apply(self.store, findings, actor="watcher")
        self.assertFalse(applied[0].applied)
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")
        self.assertEqual(
            (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8"), before)


class ScanHeartbeatTests(Base):
    def test_fresh_heartbeat_no_finding(self):
        self.running_task()
        heartbeat.beat(self.tmp, "BRIDGE-900", "RUN-01",
                       now=T0, schema_dir=SCHEMA_DIR)
        self.assertEqual(
            watcher.scan(self.store, self.policy,
                         now=T0 + timedelta(seconds=60)), [])

    def test_stale_heartbeat_flagged_and_applied_without_result(self):
        self.running_task()
        heartbeat.beat(self.tmp, "BRIDGE-900", "RUN-01",
                       now=T0, schema_dir=SCHEMA_DIR)
        now = T0 + timedelta(seconds=self.policy["heartbeat_timeout_seconds"] + 1)
        findings = watcher.scan(self.store, self.policy, now=now)
        self.assertEqual([(f.kind, f.target) for f in findings],
                         [("stale", "INTERRUPTED")])

        watcher.apply(self.store, findings, actor="watcher", machine="DES11")
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "INTERRUPTED")
        last = self.audit_lines()[-1]
        self.assertEqual(last["event_type"], "TASK_INTERRUPTED")
        self.assertTrue(last.get("reason"))
        self.assertFalse((self.tmp / "results" / "BRIDGE-900" / "RUN-01"
                          / "result.yaml").exists())

    def test_result_takes_priority_over_stale(self):
        self.running_task()
        heartbeat.beat(self.tmp, "BRIDGE-900", "RUN-01",
                       now=T0, schema_dir=SCHEMA_DIR)
        self.store.write_result(valid_result())
        now = T0 + timedelta(seconds=self.policy["heartbeat_timeout_seconds"] + 999)
        findings = watcher.scan(self.store, self.policy, now=now)
        self.assertEqual([f.kind for f in findings], ["result"])

    def test_broken_heartbeat_during_scan_fails_closed(self):
        self.running_task()
        p = heartbeat.heartbeat_path(self.tmp, "BRIDGE-900", "RUN-01")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("nonsense{", encoding="utf-8")
        with self.assertRaises(heartbeat.HeartbeatError):
            watcher.scan(self.store, self.policy, now=T0)

    def test_missing_heartbeat_beyond_grace_flags_stale(self):
        self.running_task()
        (self.tmp / "results" / "BRIDGE-900" / "RUN-01").mkdir(parents=True)
        started = watcher._run_started_at(self.store, "BRIDGE-900")
        self.assertIsNotNone(started)
        timeout = self.policy["heartbeat_timeout_seconds"]
        self.assertEqual(
            watcher.scan(self.store, self.policy,
                         now=started + timedelta(seconds=10)), [])
        findings = watcher.scan(self.store, self.policy,
                                now=started + timedelta(seconds=timeout + 5))
        self.assertEqual([f.kind for f in findings], ["stale"])


class LoopTests(Base):
    def test_loop_max_iterations_scans_twice_without_real_sleep(self):
        self.running_task()
        slept = []
        with mock.patch.object(watcher, "scan", wraps=watcher.scan) as spy:
            runs = watcher.loop(self.store, self.policy, interval=999,
                                max_iterations=2, now=lambda: T0,
                                sleep=lambda s: slept.append(s))
        self.assertEqual(spy.call_count, 2)
        self.assertEqual(len(runs), 2)
        self.assertEqual(slept, [999])  # nur zwischen den zwei Durchläufen


class CliWatchTests(Base):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp),
                         "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def test_heartbeat_cli_writes_file(self):
        self.running_task()
        code, _, err = self.cli("watch", "heartbeat", "BRIDGE-900", "RUN-01",
                                "--actor", "codex")
        self.assertEqual(code, 0, err)
        self.assertTrue(
            heartbeat.heartbeat_path(self.tmp, "BRIDGE-900", "RUN-01").exists())

    def test_scan_dry_run_changes_nothing(self):
        self.running_task()
        self.store.write_result(valid_result())
        code, out, _ = self.cli("watch", "scan")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-900", out)
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")

    def test_scan_apply_requires_actor(self):
        self.running_task()
        code, _, err = self.cli("watch", "scan", "--apply")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)

    def test_scan_apply_sets_status(self):
        self.running_task()
        self.store.write_result(valid_result())
        code, _, err = self.cli("watch", "scan", "--apply", "--actor", "watcher")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
