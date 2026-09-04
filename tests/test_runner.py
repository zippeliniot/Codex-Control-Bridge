"""Hermetische Tests für den Runner (BRIDGE-009). stdlib unittest.

Zeit über now (datetime) und Git über git_info_fn injiziert - kein echtes
Warten, kein echtes Git.
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

from bridge import heartbeat, importer, runner  # noqa: E402
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


def git_stub(root=None, base_head=None):
    return {
        "repository": "Codex-Control-Bridge", "branch": "feature/runner",
        "head": "a" * 40, "base_head": base_head,
        "commits": [], "changed_files": [],
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-runner-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()
        self.store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        self.store.create_task(valid_task())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def audit_types(self, task_id="BRIDGE-900"):
        f = self.tmp / "audit" / "audit.jsonl"
        out = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ev = json.loads(line)
                if ev.get("bridge_task_id") == task_id:
                    out.append(ev["event_type"])
        return out

    def interrupt_draft(self, **over):
        d = {"interruption_reason": "USAGE_LIMIT", "resumable": True}
        d.update(over)
        return d


class StartTests(Base):
    def test_start_from_created(self):
        run_id = runner.start(self.store, "BRIDGE-900", "a", machine="DES11", now=T0)
        self.assertEqual(run_id, "RUN-01")
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")
        self.assertTrue(
            heartbeat.heartbeat_path(self.tmp, "BRIDGE-900", "RUN-01").exists())
        self.assertEqual(self.audit_types(),
                         ["TASK_CREATED", "TASK_READY", "TASK_CLAIMED", "TASK_STARTED"])

    def test_start_from_claimed_only_missing_step(self):
        self.store.set_status("BRIDGE-900", "READY", actor="a")
        self.store.set_status("BRIDGE-900", "CLAIMED", actor="a")
        runner.start(self.store, "BRIDGE-900", "a", now=T0)
        self.assertEqual(self.audit_types(),
                         ["TASK_CREATED", "TASK_READY", "TASK_CLAIMED", "TASK_STARTED"])

    def test_start_on_running_fails_closed(self):
        runner.start(self.store, "BRIDGE-900", "a", now=T0)
        with self.assertRaises(runner.RunnerError):
            runner.start(self.store, "BRIDGE-900", "a", now=T0)


class BeatTests(Base):
    def test_beat_updates_last_seen_of_current_run(self):
        runner.start(self.store, "BRIDGE-900", "a", now=T0)
        d = runner.beat(self.store, "BRIDGE-900", actor="a",
                        now=T0 + timedelta(minutes=3))
        self.assertEqual(d["run_id"], "RUN-01")
        self.assertEqual(d["last_seen"], "2026-01-01T00:03:00Z")
        self.assertEqual(
            heartbeat.read_heartbeat(self.tmp, "BRIDGE-900", "RUN-01")["last_seen"],
            "2026-01-01T00:03:00Z")

    def test_beat_not_running_fails(self):
        with self.assertRaises(runner.RunnerError):
            runner.beat(self.store, "BRIDGE-900", actor="a")


class FinishTests(Base):
    def test_finish_completed_writes_result_and_status(self):
        runner.start(self.store, "BRIDGE-900", "a", now=T0)
        result, event = runner.finish(
            self.store, "BRIDGE-900", "COMPLETED",
            actor="a", git_info_fn=git_stub, summary="fertig")
        self.assertEqual(result["run_id"], "RUN-01")
        self.assertEqual(result["started_at"], "2026-01-01T00:00:00Z")  # aus Heartbeat
        self.assertEqual(result["summary"], "fertig")
        self.assertTrue((self.tmp / "results" / "BRIDGE-900" / "RUN-01"
                         / "result.yaml").exists())
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "COMPLETED")
        self.assertEqual(event["new_state"], "COMPLETED")
        self.assertIn("TASK_COMPLETED", self.audit_types())

    def test_finish_disallowed_transition_writes_nothing(self):
        runner.start(self.store, "BRIDGE-900", "a", now=T0)
        before = (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        with self.assertRaises(runner.RunnerError):
            runner.finish(self.store, "BRIDGE-900", "READY",
                          actor="a", git_info_fn=git_stub)
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")
        self.assertFalse((self.tmp / "results" / "BRIDGE-900" / "RUN-01"
                          / "result.yaml").exists())
        self.assertEqual(
            (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8"), before)

    def test_finish_not_running_fails(self):
        with self.assertRaises(runner.RunnerError):
            runner.finish(self.store, "BRIDGE-900", "COMPLETED",
                          actor="a", git_info_fn=git_stub)


class ResumeTests(Base):
    def _interrupt(self):
        runner.start(self.store, "BRIDGE-900", "a", now=T0)
        runner.finish(self.store, "BRIDGE-900", "INTERRUPTED", actor="a",
                      git_info_fn=git_stub,
                      draft=self.interrupt_draft(resume_hint="ab Kriterium 2"))

    def test_resume_from_interrupted(self):
        self._interrupt()
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "INTERRUPTED")
        new_run = runner.resume(self.store, "BRIDGE-900", "a",
                                now=T0 + timedelta(hours=1))
        self.assertEqual(new_run, "RUN-02")
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "RUNNING")
        self.assertEqual(
            heartbeat.read_heartbeat(self.tmp, "BRIDGE-900", "RUN-02")["last_seen"],
            "2026-01-01T01:00:00Z")
        types = self.audit_types()
        self.assertIn("TASK_WAITING_FOR_RESUME", types)
        self.assertIn("TASK_RESUMED", types)
        self.assertLess(types.index("TASK_WAITING_FOR_RESUME"),
                        types.index("TASK_RESUMED"))

    def test_resume_from_non_resumable_status_fails(self):
        with self.assertRaises(runner.RunnerError):   # frischer Task ist CREATED
            runner.resume(self.store, "BRIDGE-900", "a")

    def test_resume_hint_surfaces_from_last_result(self):
        self._interrupt()
        self.assertEqual(runner.last_resume_hint(self.store, "BRIDGE-900"),
                         "ab Kriterium 2")


class RunIdInterplayTests(Base):
    def test_start_finish_resume_run_ids(self):
        self.assertIsNone(runner.current_run_id(self.store, "BRIDGE-900"))
        self.assertEqual(runner.start(self.store, "BRIDGE-900", "a", now=T0), "RUN-01")
        self.assertEqual(runner.current_run_id(self.store, "BRIDGE-900"), "RUN-01")
        runner.finish(self.store, "BRIDGE-900", "INTERRUPTED", actor="a",
                      git_info_fn=git_stub, draft=self.interrupt_draft())
        self.assertEqual(self.store.next_run_id("BRIDGE-900"), "RUN-02")
        self.assertEqual(runner.resume(self.store, "BRIDGE-900", "a", now=T0), "RUN-02")
        self.assertEqual(runner.current_run_id(self.store, "BRIDGE-900"), "RUN-02")


class CliRunTests(Base):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp),
                         "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def test_run_start_beat_finish(self):
        code, _, err = self.cli("run", "start", "BRIDGE-900", "--actor", "a")
        self.assertEqual(code, 0, err)
        code, _, err = self.cli("run", "beat", "BRIDGE-900", "--actor", "a")
        self.assertEqual(code, 0, err)
        with mock.patch.object(importer, "collect_git_info", git_stub):
            code, out, err = self.cli("run", "finish", "BRIDGE-900",
                                      "--status", "COMPLETED", "--actor", "a")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.store.load_task("BRIDGE-900")["status"], "COMPLETED")

    def test_run_start_requires_actor(self):
        code, _, err = self.cli("run", "start", "BRIDGE-900")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)

    def test_run_beat_requires_actor(self):
        self.cli("run", "start", "BRIDGE-900", "--actor", "a")
        code, _, err = self.cli("run", "beat", "BRIDGE-900")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)

    def test_run_finish_disallowed_via_cli(self):
        self.cli("run", "start", "BRIDGE-900", "--actor", "a")
        with mock.patch.object(importer, "collect_git_info", git_stub):
            code, _, err = self.cli("run", "finish", "BRIDGE-900",
                                    "--status", "READY", "--actor", "a")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
