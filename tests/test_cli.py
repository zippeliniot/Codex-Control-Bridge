"""Hermetische Tests für die CLI (BRIDGE-006). stdlib unittest, tempdir als --root."""

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

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


def result_doc(**over):
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
        self.assertTrue((self.tmp / "tasks" / "BRIDGE-900" / "task.yaml").exists())
        code, _, err = self.cli("task", "create", str(path))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def test_task_list(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        code, out, _ = self.cli("task", "list")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-900", out)
        self.assertIn("CREATED", out)

    def test_task_show_unknown(self):
        code, _, err = self.cli("task", "show", "BRIDGE-404")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    # -- set-status ------------------------------------------------

    def test_set_status_allowed_then_disallowed(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        code, _, _ = self.cli("task", "set-status", "BRIDGE-900", "READY", "--actor", "x")
        self.assertEqual(code, 0)
        _, out, _ = self.cli("task", "show", "BRIDGE-900")
        self.assertIn("status: READY", out)
        code, _, err = self.cli("task", "set-status", "BRIDGE-900", "RUNNING", "--actor", "x")
        self.assertEqual(code, 1)
        _, out, _ = self.cli("task", "show", "BRIDGE-900")
        self.assertIn("status: READY", out)

    # -- result / next-run --------------------------------------

    def test_result_write_and_next_run(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        _, out, _ = self.cli("next-run", "BRIDGE-900")
        self.assertEqual(out.strip(), "RUN-01")
        code, _, _ = self.cli("result", "write", str(self.write_yaml("r.yaml", result_doc())))
        self.assertEqual(code, 0)
        _, out, _ = self.cli("next-run", "BRIDGE-900")
        self.assertEqual(out.strip(), "RUN-02")

    def test_result_write_without_task(self):
        code, _, err = self.cli("result", "write", str(self.write_yaml("r.yaml", result_doc())))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    # -- audit ---------------------------------------------------

    def test_audit_show_filter(self):
        self.cli("task", "create", str(self.write_yaml("a.yaml", task_doc())))
        self.cli("task", "create", str(self.write_yaml(
            "b.yaml", task_doc(bridge_task_id="BRIDGE-901"))))
        code, out, _ = self.cli("audit", "show", "BRIDGE-900")
        self.assertEqual(code, 0)
        lines = [x for x in out.splitlines() if x.strip()]
        self.assertTrue(lines)
        self.assertTrue(all("BRIDGE-900" in x for x in lines))
        self.assertFalse(any("BRIDGE-901" in x for x in lines))

    # -- resume ------------------------------------------------

    def test_resume(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        (self.tmp / "work-packages").mkdir()
        (self.tmp / "work-packages" / "BRIDGE-900.md").write_text(
            "# BRIDGE-900\n- [x] fertig\n- [ ] offen A\n- [ ] offen B\n", encoding="utf-8")
        code, out, _ = self.cli("resume", "BRIDGE-900")
        self.assertEqual(code, 0)
        self.assertIn("CREATED", out)
        self.assertIn("RUN-01", out)
        self.assertIn("offen A", out)
        self.assertIn("1 erledigt, 2 offen", out)

    def test_resume_missing_work_package(self):
        self.cli("task", "create", str(self.write_yaml("t.yaml", task_doc())))
        code, out, _ = self.cli("resume", "BRIDGE-900")
        self.assertEqual(code, 0)
        self.assertIn("nicht gefunden", out)

    # -- Nutzungsfehler --------------------------------------

    def test_usage_errors(self):
        self.assertEqual(main([]), 2)
        self.assertEqual(main(["--root", str(self.tmp), "bogus"]), 2)
        self.assertEqual(
            main(["--root", str(self.tmp), "task", "set-status", "BRIDGE-900", "READY"]), 2)


if __name__ == "__main__":
    unittest.main()
