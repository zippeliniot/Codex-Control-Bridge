"""Hermetische Tests für den Result-Importer (BRIDGE-007). stdlib unittest.

Der Git-Zugriff wird über git_info_fn bzw. Monkeypatch von
importer.collect_git_info gestubbt - kein echtes Git nötig.
"""

import io
import re
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

from bridge import importer  # noqa: E402
from bridge.cli import main  # noqa: E402
from bridge.store import Store, StoreError, SchemaValidationError  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"
TS = "2026-01-01T00:00:00Z"
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


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


def git_stub(root=None, base_head=None):
    return {
        "repository": "Codex-Control-Bridge",
        "branch": "feature/importer",
        "head": "a" * 40,
        "base_head": base_head,
        "commits": [
            {"sha": "b" * 40, "message": "erster commit"},
            {"sha": "c" * 40, "message": "zweiter commit"},
        ],
        "changed_files": ["src/bridge/importer.py", "tests/test_importer.py"],
    }


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-importer-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()
        self.store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        self.store.create_task(valid_task())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def audit_types(self):
        f = self.tmp / "audit" / "audit.jsonl"
        return [yaml.safe_load(x)["event_type"]
                for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]

    def result_on_disk(self, run_id="RUN-01"):
        path = self.tmp / "results" / "BRIDGE-900" / run_id / "result.yaml"
        return path, yaml.safe_load(path.read_text(encoding="utf-8"))

    # -- Grundfall -----------------------------------------------------

    def test_completed_draft_writes_valid_result_and_audit(self):
        res = importer.import_result(
            self.store, "BRIDGE-900", "COMPLETED",
            draft={"summary": "fertig", "started_at": TS},
            git_info_fn=git_stub,
        )
        path, doc = self.result_on_disk()
        self.assertTrue(path.exists())
        self.assertEqual(doc, res)
        self.store.validate(doc)  # schema-valide
        self.assertIn("RESULT_WRITTEN", self.audit_types())
        self.assertEqual(doc["summary"], "fertig")

    def test_project_id_taken_from_task(self):
        doc = importer.build_result(self.store, "BRIDGE-900", "COMPLETED",
                                    git_info_fn=git_stub)
        self.assertEqual(doc["project_id"], "codex-control-bridge")

    def test_run_id_default_and_explicit(self):
        importer.import_result(self.store, "BRIDGE-900", "COMPLETED",
                               git_info_fn=git_stub)
        _, doc = self.result_on_disk("RUN-01")
        self.assertEqual(doc["run_id"], "RUN-01")
        importer.import_result(self.store, "BRIDGE-900", "COMPLETED",
                               run_id="RUN-07", git_info_fn=git_stub)
        _, doc = self.result_on_disk("RUN-07")
        self.assertEqual(doc["run_id"], "RUN-07")

    def test_timestamps(self):
        doc = importer.build_result(
            self.store, "BRIDGE-900", "COMPLETED",
            draft={"started_at": "2025-12-31T09:00:00Z"}, git_info_fn=git_stub,
        )
        self.assertRegex(doc["ended_at"], RFC3339)
        self.assertEqual(doc["started_at"], "2025-12-31T09:00:00Z")

    def test_started_at_defaults_to_ended_at(self):
        doc = importer.build_result(self.store, "BRIDGE-900", "COMPLETED",
                                    git_info_fn=git_stub)
        self.assertEqual(doc["started_at"], doc["ended_at"])

    def test_git_fields_from_stub(self):
        doc = importer.build_result(self.store, "BRIDGE-900", "COMPLETED",
                                    git_info_fn=git_stub)
        self.assertEqual(doc["repository"], "Codex-Control-Bridge")
        self.assertEqual(doc["branch"], "feature/importer")
        self.assertEqual(doc["head"], "a" * 40)
        self.assertEqual([c["sha"] for c in doc["commits"]], ["b" * 40, "c" * 40])
        self.assertEqual(doc["changed_files"],
                         ["src/bridge/importer.py", "tests/test_importer.py"])

    def test_flag_beats_draft(self):
        doc = importer.build_result(
            self.store, "BRIDGE-900", "COMPLETED",
            draft={"summary": "aus entwurf"}, summary="aus flag",
            git_info_fn=git_stub,
        )
        self.assertEqual(doc["summary"], "aus flag")

    # -- INTERRUPTED / fail-closed -----------------------------------

    def test_interrupted_without_reason_fails_closed(self):
        with self.assertRaises(SchemaValidationError):
            importer.import_result(self.store, "BRIDGE-900", "INTERRUPTED",
                                   git_info_fn=git_stub)
        self.assertFalse((self.tmp / "results" / "BRIDGE-900" / "RUN-01").exists())

    def test_interrupted_with_reason_and_resumable_ok(self):
        doc = importer.import_result(
            self.store, "BRIDGE-900", "INTERRUPTED",
            draft={"interruption_reason": "USAGE_LIMIT", "resumable": True,
                   "resume_hint": "ab Kriterium 3"},
            git_info_fn=git_stub,
        )
        self.assertEqual(doc["interruption_reason"], "USAGE_LIMIT")
        self.assertTrue(doc["resumable"])

    def test_unknown_task_fails_closed(self):
        with self.assertRaises(StoreError):
            importer.import_result(self.store, "BRIDGE-404", "COMPLETED",
                                   git_info_fn=git_stub)

    def test_git_error_fails_closed(self):
        def boom(root=None, base_head=None):
            raise importer.ImporterError("git kaputt")
        with self.assertRaises(importer.ImporterError):
            importer.import_result(self.store, "BRIDGE-900", "COMPLETED",
                                   git_info_fn=boom)

    # -- CLI --------------------------------------------------------

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp),
                         "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def test_cli_import_completed(self):
        with mock.patch.object(importer, "collect_git_info", git_stub):
            code, out, err = self.cli("result", "import", "BRIDGE-900",
                                      "--status", "COMPLETED")
        self.assertEqual(code, 0, err)
        self.assertIn("RUN-01", out)
        self.assertTrue((self.tmp / "results" / "BRIDGE-900" / "RUN-01"
                         / "result.yaml").exists())

    def test_cli_import_without_status_is_usage_error(self):
        with mock.patch.object(importer, "collect_git_info", git_stub):
            code, _, err = self.cli("result", "import", "BRIDGE-900")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
