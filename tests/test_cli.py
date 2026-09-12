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
from bridge import cli as cli_mod  # noqa: E402

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
        # BRIDGE-028: Prio-Spalte vor Projekt-Spalte; Zeile: "1  MEDIUM BRIDGE..."
        second_line = out.splitlines()[1]
        self.assertTrue("BRIDGE" in second_line, second_line)

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

    # -- board --watch (BRIDGE-018) -------------------------

    def test_board_watch_runs_fixed_iterations_without_real_sleep(self):
        self.cli("task", "create", str(self.write_yaml(
            "t1.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        slept = []
        with mock.patch.object(cli_mod.time, "sleep",
                               side_effect=lambda s: slept.append(s)):
            code, out, _ = self.cli("board", "--watch", "--interval", "999",
                                    "--max-iterations", "3")
        self.assertEqual(code, 0)
        self.assertEqual(slept, [999, 999])  # nur zwischen den drei Durchlaeufen
        self.assertEqual(out.count("=== bridge board (Aktualisiert:"), 3)
        self.assertIn("BRIDGE-0901", out)

    def test_board_watch_keyboardinterrupt_exits_cleanly(self):
        self.cli("task", "create", str(self.write_yaml(
            "t1.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        with mock.patch.object(cli_mod.time, "sleep",
                               side_effect=KeyboardInterrupt):
            code, out, err = self.cli("board", "--watch", "--interval", "999")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("=== bridge board (Aktualisiert:", out)

    def test_board_without_watch_has_no_timestamp_header(self):
        self.cli("task", "create", str(self.write_yaml(
            "t1.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertNotIn("===", out)
        self.assertIn("BRIDGE-0901", out)

    # -- board Führung/Prüfung-Spalte (BRIDGE-019) ----------

    def _write_ccb_profile(self, **extra):
        pdir = self.tmp / "projects" / "codex-control-bridge"
        pdir.mkdir(parents=True, exist_ok=True)
        doc = {
            "schema_version": "1.0", "kind": "bridge_project_profile",
            "project_id": "codex-control-bridge", "repository": "X",
            "default_branch": "main", "task_prefix": "BRIDGE", "read_only": False,
        }
        doc.update(extra)
        (pdir / "project.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    def test_board_review_roles_column_from_profile(self):
        self._write_ccb_profile(
            review_roles={"lead": "openai", "support": "anthropic"})
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("Führung/Prüfung", out)
        self.assertIn("Lead: OpenAI · Support: Anthropic", out)

    def test_board_review_roles_task_override_wins(self):
        self._write_ccb_profile(
            review_roles={"lead": "anthropic", "support": "human"})
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0901",
                               review_roles={"lead": "openai", "support": None}))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("Lead: OpenAI (kein Support)", out)

    def test_board_review_roles_none_is_clearly_marked(self):
        self._write_ccb_profile()  # kein review_roles
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0901"))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("(keine Rollentrennung)", out)

    def test_board_review_roles_failsoft_without_profile(self):
        self.cli("task", "create", str(self.write_yaml(
            "t.yaml", task_doc(bridge_task_id="BRIDGE-0901",
                               project_id="voellig-unbekannt"))))
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertNotIn("(keine Rollentrennung)", out)
        self.assertIn("?", out)  # fail-soft-Markierung in der Spalte

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


# --------------------------------------------------------------------------- #
# CLI --commit Flag (BRIDGE-025)
# --------------------------------------------------------------------------- #

def _setup_git_repo_for_cli(tmp: Path) -> Path:
    """Initialisiert Working-Repo + bare-Repo als 'origin'. Gibt bare-Pfad zurueck."""
    import subprocess
    bare = Path(tempfile.mkdtemp(prefix="ccb-cli-bare-"))

    def _g(*args, cwd=tmp):
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} fehlgeschlagen: {r.stderr.strip()}")
        return r.stdout.strip()

    _g("init", "-b", "main")
    _g("config", "user.email", "test@example.com")
    _g("config", "user.name", "Test")
    (tmp / "README.md").write_text("init\n", encoding="utf-8")
    _g("add", "README.md")
    _g("commit", "-m", "initial")
    _g("clone", "--bare", str(tmp), str(bare), cwd=tmp)
    _g("remote", "add", "origin", str(bare))
    _g("push", "--set-upstream", "origin", "main")
    return bare


# --------------------------------------------------------------------------- #
# bridge overview Tests (BRIDGE-026)
# --------------------------------------------------------------------------- #

class CliOverviewTests(unittest.TestCase):
    """Prueft `bridge overview`: alle Zustaende inkl. RUNNING/CLAIMED,
    Maschinen-Anzeige, Sortierung, --project-Filter (BRIDGE-026)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-overview-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()

    def tearDown(self):
        import shutil
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

    def _make_task(self, task_id, target_status=None):
        """Erstellt und optional weiterschalten eines Auftrags."""
        path = self.write_yaml(f"{task_id}.yaml", task_doc(bridge_task_id=task_id))
        self.cli("task", "create", str(path))
        _STATUS_CHAIN = [
            "CLAIMED", "RUNNING", "COMPLETED", "WAITING_FOR_COPY_TO_CONTROL",
            "REVIEW_REQUIRED", "ARCHIVED",
        ]
        if target_status and target_status in _STATUS_CHAIN:
            for st in _STATUS_CHAIN:
                self.cli("task", "set-status", task_id, st, "--actor", "x")
                if st == target_status:
                    break

    # Abgrenzungstest: overview zeigt RUNNING/CLAIMED, board versteckt sie
    def test_overview_shows_running_claimed_hidden_from_board(self):
        self._make_task("BRIDGE-0901")   # -> WAITING_FOR_HANDOFF_TO_EXECUTOR
        self.cli("task", "set-status", "BRIDGE-0901", "CLAIMED", "--actor", "x")
        self.cli("task", "set-status", "BRIDGE-0901", "RUNNING", "--actor", "x")

        # board verbirgt RUNNING
        _, board_out, _ = self.cli("board")
        self.assertNotIn("BRIDGE-0901", board_out)
        self.assertIn("(keine Auftraege warten auf Kopie)", board_out)

        # overview zeigt RUNNING
        code, out, _ = self.cli("overview")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-0901", out)
        self.assertIn("RUNNING", out)

    def test_overview_shows_all_statuses(self):
        self._make_task("BRIDGE-0901")   # WAITING_FOR_HANDOFF_TO_EXECUTOR
        self._make_task("BRIDGE-0902", target_status="RUNNING")
        self._make_task("BRIDGE-0903", target_status="WAITING_FOR_COPY_TO_CONTROL")
        self._make_task("BRIDGE-0904", target_status="ARCHIVED")

        code, out, _ = self.cli("overview")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-0901", out)
        self.assertIn("BRIDGE-0902", out)
        self.assertIn("BRIDGE-0903", out)
        self.assertIn("BRIDGE-0904", out)

    # Sortierung: aktiver (RUNNING) oben, inaktiver (WAITING_FOR_RESUME) unten
    def test_overview_sort_active_before_inactive(self):
        from datetime import datetime, timezone, timedelta
        from bridge.cli import _overview_rows
        from bridge.store import Store

        # BRIDGE-0901: RUNNING mit frischem Heartbeat -> aktiv
        self._make_task("BRIDGE-0901", target_status="RUNNING")
        hb_dir = self.tmp / "results" / "BRIDGE-0901" / "RUN-01"
        hb_dir.mkdir(parents=True, exist_ok=True)
        import json
        now = datetime.now(timezone.utc)
        (hb_dir / "heartbeat.json").write_text(json.dumps({
            "kind": "bridge_heartbeat",
            "bridge_task_id": "BRIDGE-0901",
            "run_id": "RUN-01",
            "last_seen": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }), encoding="utf-8")

        # BRIDGE-0902: WAITING_FOR_RESUME -> immer inaktiv
        self._make_task("BRIDGE-0902", target_status="RUNNING")
        self.cli("task", "set-status", "BRIDGE-0902", "WAITING_FOR_RESUME", "--actor", "x")

        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _overview_rows(store, now=now)
        ids = [r[0] for r in rows]
        # BRIDGE-0901 (aktiv) muss vor BRIDGE-0902 (inaktiv) kommen
        self.assertIn("BRIDGE-0901", ids)
        self.assertIn("BRIDGE-0902", ids)
        self.assertLess(ids.index("BRIDGE-0901"), ids.index("BRIDGE-0902"))

    # Sortierung: RUNNING mit altem Heartbeat gilt als inaktiv
    def test_overview_stale_heartbeat_is_inactive(self):
        from datetime import datetime, timezone, timedelta
        from bridge.cli import _overview_rows, _OVERVIEW_INACTIVE_THRESHOLD_MINUTES
        from bridge.store import Store
        import json

        self._make_task("BRIDGE-0901", target_status="RUNNING")
        hb_dir = self.tmp / "results" / "BRIDGE-0901" / "RUN-01"
        hb_dir.mkdir(parents=True, exist_ok=True)
        stale_ts = (datetime.now(timezone.utc)
                    - timedelta(minutes=_OVERVIEW_INACTIVE_THRESHOLD_MINUTES + 5))
        (hb_dir / "heartbeat.json").write_text(json.dumps({
            "kind": "bridge_heartbeat",
            "bridge_task_id": "BRIDGE-0901",
            "run_id": "RUN-01",
            "last_seen": stale_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }), encoding="utf-8")

        # BRIDGE-0902: RUNNING mit frischem Heartbeat
        self._make_task("BRIDGE-0902", target_status="RUNNING")
        hb_dir2 = self.tmp / "results" / "BRIDGE-0902" / "RUN-01"
        hb_dir2.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        (hb_dir2 / "heartbeat.json").write_text(json.dumps({
            "kind": "bridge_heartbeat",
            "bridge_task_id": "BRIDGE-0902",
            "run_id": "RUN-01",
            "last_seen": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }), encoding="utf-8")

        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _overview_rows(store, now=now)
        ids = [r[0] for r in rows]
        is_active = {r[0]: r[6] for r in rows}
        # frischer HB -> aktiv, alter HB -> inaktiv
        self.assertTrue(is_active.get("BRIDGE-0902"), "BRIDGE-0902 muss aktiv sein")
        self.assertFalse(is_active.get("BRIDGE-0901"), "BRIDGE-0901 muss inaktiv sein (alter HB)")
        self.assertLess(ids.index("BRIDGE-0902"), ids.index("BRIDGE-0901"))

    # Fehlendes machine-Feld -> '?' (kein Erfinden)
    def test_overview_missing_machine_shown_as_question_mark(self):
        self._make_task("BRIDGE-0901")
        code, out, _ = self.cli("overview")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-0901", out)
        self.assertIn("?", out)   # '?' bei fehlendem machine-Feld

    # --project Filter
    def test_overview_project_filter(self):
        self._make_task("BRIDGE-0901")   # project_id = codex-control-bridge
        path2 = self.write_yaml("T2.yaml", task_doc(
            bridge_task_id="BRIDGE-0902", project_id="anderes-projekt"))
        self.cli("task", "create", str(path2))

        code, out, _ = self.cli("overview", "--project", "codex-control-bridge")
        self.assertEqual(code, 0)
        self.assertIn("BRIDGE-0901", out)
        self.assertNotIn("BRIDGE-0902", out)

    # Leerer Store -> kein Absturz
    def test_overview_empty_store(self):
        code, out, _ = self.cli("overview")
        self.assertEqual(code, 0)
        self.assertIn("(keine Auftraege)", out)

    # Trennlinie erscheint nur wenn aktive und inaktive Auftraege gemischt sind
    def test_overview_separator_between_active_and_inactive(self):
        from datetime import datetime, timezone
        import json
        from bridge.cli import _overview_text, _overview_rows
        from bridge.store import Store

        self._make_task("BRIDGE-0901", target_status="RUNNING")
        hb_dir = self.tmp / "results" / "BRIDGE-0901" / "RUN-01"
        hb_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        (hb_dir / "heartbeat.json").write_text(json.dumps({
            "kind": "bridge_heartbeat",
            "bridge_task_id": "BRIDGE-0901",
            "run_id": "RUN-01",
            "last_seen": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }), encoding="utf-8")
        self._make_task("BRIDGE-0902", target_status="ARCHIVED")

        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _overview_rows(store, now=now)
        text = _overview_text(rows)
        self.assertIn("--- inaktiv / unterbrochen ---", text)


class CliPriorityTests(unittest.TestCase):
    """Prueft 'bridge task set-priority' und Prioritaets-Sortierung (BRIDGE-028)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-prio-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()

    def tearDown(self):
        import shutil
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

    def _make_task(self, task_id, **extra):
        path = self.write_yaml(f"{task_id}.yaml",
                               task_doc(bridge_task_id=task_id, **extra))
        self.cli("task", "create", str(path))

    def test_set_priority_changes_field_and_exits_0(self):
        """set-priority setzt das Feld und gibt Exit 0 zurueck."""
        self._make_task("BRIDGE-0901")
        code, out, err = self.cli("task", "set-priority", "BRIDGE-0901", "HIGH",
                                  "--actor", "test")
        self.assertEqual(code, 0, err)
        self.assertIn("HIGH", out)

    def test_set_priority_writes_audit_entry(self):
        """Nach set-priority steht PRIORITY_CHANGED in der Auditspur."""
        from bridge.store import Store
        self._make_task("BRIDGE-0901")
        self.cli("task", "set-priority", "BRIDGE-0901", "HIGH", "--actor", "test")
        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        import json
        events = [json.loads(l) for l in
                  (self.tmp / "audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
                  if l.strip()]
        types = [e["event_type"] for e in events]
        self.assertIn("PRIORITY_CHANGED", types)

    def test_set_priority_invalid_value_rejected(self):
        """Ungueltige Prioritaet wird mit Exit 2 (usage-Fehler) abgelehnt."""
        self._make_task("BRIDGE-0901")
        code, _, _ = self.cli("task", "set-priority", "BRIDGE-0901", "URGENT",
                               "--actor", "test")
        self.assertNotEqual(code, 0)

    def test_overview_sort_high_before_low_same_group(self):
        """Innerhalb der inaktiven Gruppe: HIGH sortiert vor LOW."""
        from bridge.cli import _overview_rows
        from bridge.store import Store
        # Beide WAITING_FOR_HANDOFF (inaktiv)
        self._make_task("BRIDGE-0901", priority="LOW")
        self._make_task("BRIDGE-0902", priority="HIGH")
        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _overview_rows(store)
        ids = [r[0] for r in rows]
        self.assertLess(ids.index("BRIDGE-0902"), ids.index("BRIDGE-0901"),
                        f"HIGH (0902) soll vor LOW (0901) stehen, war: {ids}")

    def test_board_sort_high_before_low(self):
        """Im Board: HIGH-Auftrag steht vor LOW-Auftrag (beide WAITING_FOR_HANDOFF)."""
        from bridge.cli import _board_rows
        from bridge.store import Store
        self._make_task("BRIDGE-0901", priority="LOW")
        self._make_task("BRIDGE-0902", priority="HIGH")
        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _board_rows(store)
        ids = [r[0] for r in rows]
        self.assertLess(ids.index("BRIDGE-0902"), ids.index("BRIDGE-0901"),
                        f"HIGH (0902) soll vor LOW (0901) stehen, war: {ids}")

    def test_board_sort_task_id_tiebreaker_same_priority(self):
        """Bei gleicher Prioritaet bleibt bridge_task_id der Tie-Breaker."""
        from bridge.cli import _board_rows
        from bridge.store import Store
        self._make_task("BRIDGE-0901", priority="MEDIUM")
        self._make_task("BRIDGE-0902", priority="MEDIUM")
        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _board_rows(store)
        ids = [r[0] for r in rows]
        self.assertEqual(ids, sorted(ids))   # alphabetisch bei gleicher Prio

    def test_priority_column_in_board_text(self):
        """board-Textausgabe enthaelt die Prioritaets-Spalte."""
        self._make_task("BRIDGE-0901", priority="HIGH")
        code, out, _ = self.cli("board")
        self.assertEqual(code, 0)
        self.assertIn("HIGH", out)

    def test_priority_column_in_overview_text(self):
        """overview-Textausgabe enthaelt die Prioritaets-Spalte."""
        self._make_task("BRIDGE-0901", priority="LOW")
        code, out, _ = self.cli("overview")
        self.assertEqual(code, 0)
        self.assertIn("LOW", out)

    def test_task_without_priority_defaults_to_medium_in_overview(self):
        """Auftraege ohne priority-Feld zeigen MEDIUM als Default an."""
        self._make_task("BRIDGE-0901")  # kein priority-Feld
        from bridge.cli import _overview_rows
        from bridge.store import Store
        store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        rows = _overview_rows(store)
        self.assertEqual(rows[0][7], "MEDIUM")


class CliCommitTests(unittest.TestCase):
    """Prueft das --commit-Flag auf den 5 Subcommands (BRIDGE-025).

    Nutzt echte Git-Repos (kein Netzwerkzugriff: lokales bare-Repo als origin).
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-cli-commit-"))
        for sub in ("tasks", "results", "audit"):
            (self.tmp / sub).mkdir()
        self.bare = _setup_git_repo_for_cli(self.tmp)
        # Staging-YAML AUSSERHALB des Git-Repos (kein untracked-Artefakt im Repo)
        self._staging_dir = Path(tempfile.mkdtemp(prefix="ccb-cli-staging-"))
        doc = task_doc(git={"expected_head": "a" * 40})
        p = self._staging_dir / "t.yaml"
        p.write_text(yaml.safe_dump(doc), encoding="utf-8")
        self._staging_path = str(p)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.bare, ignore_errors=True)
        shutil.rmtree(self._staging_dir, ignore_errors=True)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp), "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def _git(self, *args):
        import subprocess
        r = subprocess.run(["git", *args], cwd=self.tmp, capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip()

    def _commit_count(self):
        return int(self._git("rev-list", "--count", "HEAD"))

    def _last_msg(self):
        return self._git("log", "-1", "--format=%s")

    def _stage_store_files(self, *paths):
        """Dateien anlegen und in Git stagen (damit git status sie zeigt)."""
        import subprocess
        for rel in paths:
            p = self.tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text("x\n", encoding="utf-8")
        # Kein add hier - die Dateien sind untracked/modified nach CLI-Aufruf

    # --- task create --commit -----------------------------------------------

    def test_task_create_commit(self):
        count_before = self._commit_count()
        code, out, err = self.cli("task", "create", self._staging_path, "--commit")
        self.assertEqual(code, 0, err)
        self.assertIn("Commit", out)
        self.assertEqual(self._commit_count(), count_before + 1)
        msg = self._last_msg()
        self.assertIn("BRIDGE-0900", msg)
        self.assertIn("task_create", msg)

    def test_task_create_without_commit_no_extra_commit(self):
        count_before = self._commit_count()
        code, _, _ = self.cli("task", "create", self._staging_path)
        self.assertEqual(code, 0)
        # Kein Commit ohne --commit
        self.assertEqual(self._commit_count(), count_before)

    # --- run start --commit -------------------------------------------------

    def test_run_start_commit(self):
        # task create (ohne --commit, manuell stagen)
        self.cli("task", "create", self._staging_path)
        import subprocess
        subprocess.run(["git", "add", "tasks/BRIDGE-0900/task.yaml", "audit/audit.jsonl"],
                       cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "manual: task create"], cwd=self.tmp,
                       capture_output=True)
        count_before = self._commit_count()

        code, out, err = self.cli("run", "start", "BRIDGE-0900", "--actor", "a", "--commit")
        self.assertEqual(code, 0, err)
        self.assertIn("Commit", out)
        self.assertEqual(self._commit_count(), count_before + 1)
        msg = self._last_msg()
        self.assertIn("BRIDGE-0900", msg)
        self.assertIn("run_start", msg)

    # --- task copied --commit -----------------------------------------------

    def test_task_copied_commit(self):
        from unittest import mock
        from bridge import importer, runner

        def git_stub(root=None, base_head=None):
            return {"repository": "Codex-Control-Bridge", "branch": "main",
                    "head": "a" * 40, "base_head": base_head,
                    "commits": [], "changed_files": []}

        # Setup: task anlegen + run starten + finishen -> WAITING_FOR_COPY_TO_CONTROL
        import subprocess, yaml as _yaml
        self.cli("task", "create", self._staging_path)
        subprocess.run(["git", "add", "tasks/BRIDGE-0900/task.yaml", "audit/audit.jsonl"],
                       cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "setup"], cwd=self.tmp, capture_output=True)

        self.cli("run", "start", "BRIDGE-0900", "--actor", "a")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "run start"], cwd=self.tmp, capture_output=True)

        with mock.patch.object(importer, "collect_git_info", git_stub):
            self.cli("run", "finish", "BRIDGE-0900", "--status", "COMPLETED",
                     "--actor", "a", "--base-head", "a" * 40)
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "run finish"], cwd=self.tmp, capture_output=True)

        count_before = self._commit_count()
        code, out, err = self.cli("task", "copied", "BRIDGE-0900", "--actor", "a", "--commit")
        self.assertEqual(code, 0, err)
        self.assertIn("Commit", out)
        self.assertEqual(self._commit_count(), count_before + 1)
        msg = self._last_msg()
        self.assertIn("task_copied", msg)

    # --- task archive --commit ----------------------------------------------

    def test_task_archive_commit(self):
        from unittest import mock
        from bridge import importer

        def git_stub(root=None, base_head=None):
            return {"repository": "Codex-Control-Bridge", "branch": "main",
                    "head": "a" * 40, "base_head": base_head,
                    "commits": [], "changed_files": []}

        import subprocess
        # Setup: task -> run start -> finish -> copied -> archive
        self.cli("task", "create", self._staging_path)
        subprocess.run(["git", "add", "tasks/BRIDGE-0900/task.yaml", "audit/audit.jsonl"],
                       cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "setup"], cwd=self.tmp, capture_output=True)

        self.cli("run", "start", "BRIDGE-0900", "--actor", "a")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "run start"], cwd=self.tmp, capture_output=True)

        with mock.patch.object(importer, "collect_git_info", git_stub):
            self.cli("run", "finish", "BRIDGE-0900", "--status", "COMPLETED",
                     "--actor", "a", "--base-head", "a" * 40)
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "finish"], cwd=self.tmp, capture_output=True)

        self.cli("task", "copied", "BRIDGE-0900", "--actor", "a")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "copied"], cwd=self.tmp, capture_output=True)

        count_before = self._commit_count()
        code, out, err = self.cli("task", "archive", "BRIDGE-0900", "--actor", "a", "--commit")
        self.assertEqual(code, 0, err)
        self.assertIn("Commit", out)
        self.assertEqual(self._commit_count(), count_before + 1)
        msg = self._last_msg()
        self.assertIn("task_archive", msg)

    # --- Whitelist-Fehler: Exit-Code 3, Store-Aktion bleibt bestehen --------

    def test_commit_whitelist_failure_exits_3_store_preserved(self):
        import subprocess
        code, _, _ = self.cli("task", "create", self._staging_path)
        self.assertEqual(code, 0)
        subprocess.run(["git", "add", "tasks/BRIDGE-0900/task.yaml", "audit/audit.jsonl"],
                       cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "setup"], cwd=self.tmp, capture_output=True)

        # Unerwartete Datei anlegen
        (self.tmp / "unrelated.txt").write_text("oops\n", encoding="utf-8")

        # run start aendert task.yaml + audit.jsonl + heartbeat, PLUS unrelated.txt ist da
        code, _, err = self.cli("run", "start", "BRIDGE-0900", "--actor", "a", "--commit")
        # Exit-Code 3: Store-Aktion war erfolgreich, Commit fehlgeschlagen
        self.assertEqual(code, 3, f"Erwartet 3, bekommen {code}: {err}")
        self.assertIn("Git-Fehler", err)
        # Store-Aktion war erfolgreich: Task ist jetzt RUNNING
        from bridge.store import Store
        task = Store(root=self.tmp, schema_dir=SCHEMA_DIR).load_task("BRIDGE-0900")
        self.assertEqual(task["status"], "RUNNING")


# --------------------------------------------------------------------------- #
# base_head-Regressionstest (BRIDGE-025)
# --------------------------------------------------------------------------- #

class BaseHeadRegressionTests(unittest.TestCase):
    """Stellt das BRIDGE-023/024-Szenario nach: mehrere Commits seit Taskerstellung,
    run finish OHNE --base-head -> changed_files muss trotzdem den gesamten Lauf abdecken.
    """

    def setUp(self):
        import subprocess, yaml as _yaml
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-basehead-"))
        for sub in ("tasks", "results", "audit"):
            (self.tmp / sub).mkdir()
        # Git-Repo initialisieren
        self._sp = lambda *args: subprocess.run(
            ["git", *args], cwd=self.tmp, capture_output=True, text=True, timeout=30)
        self._sp("init", "-b", "main")
        self._sp("config", "user.email", "test@example.com")
        self._sp("config", "user.name", "Test")
        (self.tmp / "README.md").write_text("init\n", encoding="utf-8")
        self._sp("add", "README.md")
        self._sp("commit", "-m", "initial")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _head(self):
        return self._sp("rev-parse", "HEAD").stdout.strip()

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp), "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def test_base_head_auto_derived_from_task_yaml(self):
        """Wenn --base-head fehlt, wird git.expected_head aus task.yaml verwendet."""
        from unittest import mock
        from bridge import importer
        import shutil as _shutil

        expected_head = self._head()
        doc = task_doc(git={"expected_head": expected_head})
        # Staging-YAML ausserhalb des Repos, damit sie nicht als untracked erscheint
        staging_dir = Path(tempfile.mkdtemp(prefix="ccb-staging-"))
        self.addCleanup(_shutil.rmtree, staging_dir, True)
        p = staging_dir / "t.yaml"
        p.write_text(yaml.safe_dump(doc), encoding="utf-8")

        # Task anlegen (auto-chains zu WAITING_FOR_HANDOFF_TO_EXECUTOR)
        code, _, err = self.cli("task", "create", str(p))
        self.assertEqual(code, 0, err)

        # Mehrere Commits nach Taskerstellung simulieren
        self._sp("add", "tasks/BRIDGE-0900/task.yaml", "audit/audit.jsonl")
        self._sp("commit", "-m", "commit-1")
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "feature.py").write_text("# new\n", encoding="utf-8")
        self._sp("add", "src/feature.py")
        self._sp("commit", "-m", "commit-2: new feature")
        (self.tmp / "docs").mkdir(exist_ok=True)
        (self.tmp / "docs" / "readme.md").write_text("docs\n", encoding="utf-8")
        self._sp("add", "docs/readme.md")
        self._sp("commit", "-m", "commit-3: docs")

        # run start (ohne echtes git_info_fn)
        self.cli("run", "start", "BRIDGE-0900", "--actor", "a")
        self._sp("add", "-A")
        self._sp("commit", "-m", "run start commit")

        # run finish OHNE --base-head -> soll git.expected_head nutzen
        # Mit echtem git (kein Mock): changed_files muss alle 4 Commits seit
        # expected_head abdecken.
        code, out, err = self.cli("run", "finish", "BRIDGE-0900",
                                   "--status", "COMPLETED", "--actor", "a",
                                   "--summary", "fertig")
        self.assertEqual(code, 0, err)

        # Ergebnis lesen und changed_files pruefen
        import yaml as _yaml
        result_path = self.tmp / "results" / "BRIDGE-0900" / "RUN-01" / "result.yaml"
        self.assertTrue(result_path.exists())
        result = _yaml.safe_load(result_path.read_text(encoding="utf-8"))
        changed = result.get("changed_files", [])
        # Muss mehr als nur den letzten Commit abdecken
        self.assertGreater(len(changed), 1,
            f"changed_files deckt nur {changed} ab, erwartet mind. 2 Dateien "
            f"(Regression BRIDGE-023/024: stiller Fallback auf letzten Commit)")
        # src/feature.py und docs/readme.md muessen drin sein
        self.assertIn("src/feature.py", changed, f"changed_files={changed}")
        self.assertIn("docs/readme.md", changed, f"changed_files={changed}")

    def test_missing_base_head_and_no_expected_head_fails_closed(self):
        """Wenn --base-head fehlt UND git.expected_head nicht gesetzt ist,
        schlaegt run finish fail-closed fehl (kein stiller Fallback)."""
        import shutil as _shutil
        # Task OHNE git.expected_head
        doc = task_doc()
        staging_dir = Path(tempfile.mkdtemp(prefix="ccb-staging-"))
        self.addCleanup(_shutil.rmtree, staging_dir, True)
        p = staging_dir / "t.yaml"
        p.write_text(yaml.safe_dump(doc), encoding="utf-8")
        self.cli("task", "create", str(p))
        self._sp("add", "tasks/BRIDGE-0900/task.yaml", "audit/audit.jsonl")
        self._sp("commit", "-m", "setup")
        self.cli("run", "start", "BRIDGE-0900", "--actor", "a")
        self._sp("add", "-A")
        self._sp("commit", "-m", "run start")

        # run finish ohne --base-head und ohne git.expected_head -> Exit-Code 1
        code, _, err = self.cli("run", "finish", "BRIDGE-0900",
                                "--status", "COMPLETED", "--actor", "a")
        self.assertEqual(code, 1, f"Erwartet 1 (fail-closed), bekommen {code}")
        self.assertIn("base-head", err)
        self.assertIn("fail-closed", err)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
