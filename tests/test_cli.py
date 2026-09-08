"""Hermetische Tests für die CLI (BRIDGE-006). stdlib unittest, tempdir als --root."""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from bridge.cli import main  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"
TS = "2026-01-01T00:00:00Z"


def task_doc(**over):
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


def result_doc(**over):
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


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-cli-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_yaml(self, name, doc):
        path = self.tmp / name
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        return path

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp), "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    # -- validate ----------------------------------------------------

    def test_validate_ok(self):
        path = self.write_yaml("t.yaml", task_doc())
        code, _, _ = self.cli("validate", str(path))
        self.assertEqual(code, 0)

    def test_validate_invalid_and_missing(self):
        bad = task_doc()
        del bad["title"]
        path = self.write_yaml("bad.yaml", bad)
        code, _, err = self.cli("validate", str(path))
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        code, _, _ = self.cli("validate", str(self.tmp / "nope.yaml"))
        self.assertEqual(code, 1)

    # -- task create / list / show --------------------------------

    def test_task_create_and_duplicate(self):
        path = self.write_yaml("t.yaml", task_doc())
        code, _, _ = self.cli("task", "create", str(path))
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "tasks" / "BRIDGE-0900" / "task.yaml").exists())
        code, _, err = self.cli("task", "create", str(path))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def test_task_list(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        code, out, _ = self.cli("task", "list")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-0900", out)
        # BRIDGE-014: task create schaltet automatisch bis zum Wartezustand durch.
        self.assertIn("WAITING_FOR_HANDOFF_TO_EXECUTOR", out)

    def test_task_show_unknown(self):
        code, _, err = self.cli("task", "show", "BRIDGE-0404")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    # -- set-status ------------------------------------------------

    def test_set_status_allowed_then_disallowed(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        # Auftrag steht nach create bei WAITING_FOR_HANDOFF_TO_EXECUTOR (BRIDGE-014).
        code, _, _ = self.cli("task", "set-status", "BRIDGE-0900", "CLAIMED", "--actor", "x")
        self.assertEqual(code, 0)
        _, out, _ = self.cli("task", "show", "BRIDGE-0900")
        self.assertIn("status: CLAIMED", out)
        code, _, err = self.cli("task", "set-status", "BRIDGE-0900", "COMPLETED", "--actor", "x")
        self.assertEqual(code, 1)
        _, out, _ = self.cli("task", "show", "BRIDGE-0900")
        self.assertIn("status: CLAIMED", out)

    # -- task archive (BRIDGE-017) --------------------------------

    def _walk(self, task_id, *states):
        for st in states:
            self.cli("task", "set-status", task_id, st, "--actor", "x")

    def test_task_archive_from_allowed_state(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        # WAITING_FOR_HANDOFF_TO_EXECUTOR -> ... -> REVIEW_REQUIRED (ARCHIVED erlaubt)
        self._walk("BRIDGE-0900", "CLAIMED", "RUNNING", "REVIEW_REQUIRED")
        code, out, _ = self.cli("task", "archive", "BRIDGE-0900", "--actor", "x")
        self.assertEqual(code, 0)
        self.assertIn("REVIEW_REQUIRED -> ARCHIVED", out)
        self.assertIn("TASK_ARCHIVED", out)
        _, show, _ = self.cli("task", "show", "BRIDGE-0900")
        self.assertIn("status: ARCHIVED", show)
        # Standardbegruendung landet in der Auditspur.
        _, audit, _ = self.cli("audit", "show", "BRIDGE-0900")
        self.assertIn("Auftrag abgeschlossen", audit)

    def test_task_archive_from_disallowed_state_fails_closed(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        # RUNNING -> ARCHIVED ist in der Zustandstabelle nicht gelistet.
        self._walk("BRIDGE-0900", "CLAIMED", "RUNNING")
        code, _, err = self.cli("task", "archive", "BRIDGE-0900", "--actor", "x")
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        self.assertNotIn("Traceback", err)
        _, show, _ = self.cli("task", "show", "BRIDGE-0900")
        self.assertIn("status: RUNNING", show)

    def test_task_archive_requires_actor(self):
        code = main(["--root", str(self.tmp), "--schema-dir", str(SCHEMA_DIR),
                     "task", "archive", "BRIDGE-0900"])
        self.assertEqual(code, 2)

    # -- result / next-run --------------------------------------

    def test_result_write_and_next_run(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        _, out, _ = self.cli("next-run", "BRIDGE-0900")
        self.assertEqual(out.strip(), "RUN-01")
        code, _, _ = self.cli("result", "write", str(self.write_yaml("r.yaml", result_doc())))
        self.assertEqual(code, 0)
        _, out, _ = self.cli("next-run", "BRIDGE-0900")
        self.assertEqual(out.strip(), "RUN-02")

    def test_result_write_without_task(self):
        code, _, err = self.cli("result", "write", str(self.write_yaml("r.yaml", result_doc())))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    # -- audit ---------------------------------------------------

    def test_audit_show_filter(self):
        self.cli("task", "create", str(self.write_yaml("a.yaml", task_doc())))
        self.cli("task", "create", str(self.write_yaml(
            "b.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        code, out, _ = self.cli("audit", "show", "BRIDGE-0900")
        self.assertEqual(code, 0)
        lines = [x for x in out.splitlines() if x.strip()]
        self.assertTrue(lines)
        self.assertTrue(all("BRIDGE-0900" in x for x in lines))
        self.assertFalse(any("BRIDGE-0901" in x for x in lines))

    # -- resume ------------------------------------------------

    def test_resume(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        (self.tmp / "work-packages").mkdir()
        (self.tmp / "work-packages" / "BRIDGE-0900.md").write_text(
            "# BRIDGE-0900\n- [x] fertig\n- [ ] offen A\n- [ ] offen B\n", encoding="utf-8")
        code, out, _ = self.cli("resume", "BRIDGE-0900")
        self.assertEqual(code, 0)
        self.assertIn("WAITING_FOR_HANDOFF_TO_EXECUTOR", out)
        self.assertIn("RUN-01", out)
        self.assertIn("offen A", out)
        self.assertIn("1 erledigt, 2 offen", out)

    def test_resume_missing_work_package(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        code, out, _ = self.cli("resume", "BRIDGE-0900")
        self.assertEqual(code, 0)
        self.assertIn("nicht gefunden", out)

    # -- board (BRIDGE-016) ---------------------------------

    def _walk_to_waiting_copy(self, task_id):
        for st in ("CLAIMED", "RUNNING", "COMPLETED", "WAITING_FOR_COPY_TO_CONTROL"):
            self.cli("task", "set-status", task_id, st, "--actor", "x")

    def test_board_empty_store(self):
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("(keine Auftraege warten auf Kopie)", out)

    def test_board_shows_both_waiting_states_ignores_others(self):
        self.cli("task", "create", str(self.write_yaml(
            "t1.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        self.cli("task", "create", str(self.write_yaml(
            "t2.yaml", task_doc(bridge_task_id="BRIDGE-0902"))))
        self._walk_to_waiting_copy("BRIDGE-0902")
        self.cli("task", "create", str(self.write_yaml(
            "t3.yaml", task_doc(bridge_task_id="BRIDGE-0903"))))
        self.cli("task", "set-status", "BRIDGE-0903", "CLAIMED", "--actor", "x")

        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-0901", out)
        self.assertIn("BRIDGE-0902", out)
        self.assertNotIn("BRIDGE-0903", out)
        self.assertIn("Steuerchat -> Executor", out)
        self.assertIn("Executor -> Steuerchat", out)
        # Sortierung nach bridge_task_id
        self.assertLess(out.index("BRIDGE-0901"), out.index("BRIDGE-0902"))

    def test_board_failsoft_without_profile(self):
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0901",
                               project_id="voellig-unbekannt"))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("voellig-unbekannt", out)

    def test_board_uses_task_prefix_when_profile_present(self):
        pdir = self.tmp / "projects" / "codex-control-bridge"
        pdir.mkdir(parents=True)
        (pdir / "project.yaml").write_text(yaml.safe_dump({
            "schema_version": "1.0", "kind": "bridge_project_profile",
            "project_id": "codex-control-bridge", "repository": "Codex-Control-Bridge",
            "default_branch": "main", "task_prefix": "BRIDGE", "read_only": False,
        }), encoding="utf-8")
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[1].startswith("1  BRIDGE"))

    def test_board_depends_on_note_when_not_archived(self):
        self.cli("task", "create", str(self.write_yaml(
            "dep.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0902",
                               depends_on=["BRIDGE-0901"]))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn(
            "(depends_on BRIDGE-0901, Status: WAITING_FOR_HANDOFF_TO_EXECUTOR)", out)

    def test_board_depends_on_outside_store_no_note(self):
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0902",
                               depends_on=["DORF-0001"]))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertNotIn("depends_on", out)

    # -- commands (BRIDGE-016) ------------------------------

    def _clean_env(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("CCB_PROJECT_BASE", None)
        self.addCleanup(patcher.stop)

    def test_commands_sections_with_override(self):
        self._clean_env()
        os.environ["CCB_PROJECT_BASE"] = "E:\\_DEV"
        code, out, _ = self.cli("commands")
        self.assertEqual(code, 0)
        self.assertIn("bridge board", out)
        self.assertIn("bridge watch loop", out)
        self.assertIn("handover-check.ps1", out)
        self.assertIn("handover-check.sh", out)
        self.assertIn("E:\\_DEV", out)

    def test_commands_resolves_path_and_test_command(self):
        self._clean_env()
        os.environ["CCB_PROJECT_BASE"] = "E:\\base"
        pdir = self.tmp / "projects" / "demo"
        pdir.mkdir(parents=True)
        (pdir / "project.yaml").write_text(yaml.safe_dump({
            "schema_version": "1.0", "kind": "bridge_project_profile",
            "project_id": "demo", "repository": "Demo-Repo",
            "default_branch": "main", "task_prefix": "DEMO", "read_only": True,
            "test_policy": {"command": "pytest -q", "required": True},
        }), encoding="utf-8")
        code, out, _ = self.cli("commands", "--project", "demo")
        self.assertEqual(code, 0)
        self.assertIn("Demo-Repo", out)
        self.assertIn("pytest -q", out)

    def test_commands_unknown_machine_fails_closed(self):
        self._clean_env()
        (self.tmp / "registry.yaml").write_text(
            "schema_version: '1.0'\nkind: bridge_machine_registry\n"
            "machines:\n  HAM11: 'E:\\_DEV'\n", encoding="utf-8")
        code, _, err = self.cli("commands", "--machine", "NOPE11")
        self.assertEqual(code, 1)
        self.assertIn("NOPE11", err)
        self.assertIn("CCB_PROJECT_BASE", err)
        self.assertNotIn("Traceback", err)

    # -- Nutzungsfehler --------------------------------------

    def test_usage_errors(self):
        self.assertEqual(main([]), 2)
        self.assertEqual(main(["--root", str(self.tmp), "bogus"]), 2)
        self.assertEqual(
            main(["--root", str(self.tmp), "task", "set-status", "BRIDGE-0900", "READY"]), 2)


if __name__ == "__main__":
    unittest.main()
