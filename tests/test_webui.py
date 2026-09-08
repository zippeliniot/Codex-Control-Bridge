"""Hermetische Tests fuer die Lese-Web-UI (BRIDGE-020, RUN-01). stdlib unittest.

Startet einen echten Server auf einem vom OS vergebenen Port (0), ruft ihn per
``urllib.request`` ab und faehrt ihn wieder herunter - kein Mock der HTTP-Schicht.
"""

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from bridge import webui  # noqa: E402
from bridge.cli import _board_rows, main  # noqa: E402
from bridge.store import Store  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"
TS = "2026-01-01T00:00:00Z"


def task_doc(**over):
    doc = {
        "schema_version": "1.0",
        "kind": "bridge_task",
        "bridge_task_id": "BRIDGE-0900",
        "project_id": "codex-control-bridge",
        "title": "Testauftrag",
        "description": "Nur fuer Tests.",
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


class WebUiBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-webui-"))
        for name in ("tasks", "results", "audit"):
            (self.tmp / name).mkdir()
        self.store = Store(root=self.tmp, schema_dir=SCHEMA_DIR)
        self.httpd = None
        self.thread = None

    def tearDown(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- Helfer ------------------------------------------------------

    def cli(self, *args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp), "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def make_task(self, task_id, target_status=None):
        path = self.tmp / f"{task_id}.yaml"
        path.write_text(yaml.safe_dump(task_doc(bridge_task_id=task_id)), encoding="utf-8")
        self.cli("task", "create", str(path))
        for state in _walk(target_status):
            self.cli("task", "set-status", task_id, state, "--actor", "x")

    def start(self):
        self.httpd = webui.serve(self.store, port=0, actor="tester")
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.httpd.server_address[1]

    def get(self, path):
        port = self.httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, res.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def request(self, method, path):
        port = self.httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, res.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")


# 'task create' laesst den Auftrag bereits in WAITING_FOR_HANDOFF_TO_EXECUTOR.
_WALK = {
    None: [],
    "WAITING_FOR_HANDOFF_TO_EXECUTOR": [],
    "RUNNING": ["CLAIMED", "RUNNING"],
    "WAITING_FOR_COPY_TO_CONTROL": ["CLAIMED", "RUNNING", "COMPLETED",
                                    "WAITING_FOR_COPY_TO_CONTROL"],
    "ARCHIVED": ["CLAIMED", "RUNNING", "COMPLETED", "WAITING_FOR_COPY_TO_CONTROL",
                 "REVIEW_REQUIRED", "ARCHIVED"],
}


def _walk(target):
    return _WALK[target]


class WebUiReadTests(WebUiBase):
    def test_get_root_is_offline_html(self):
        self.start()
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("<title>", body)
        self.assertIn("/api/board", body)          # Auto-Refresh-Ziel
        self.assertIn("setInterval", body)
        self.assertIn("15000", body)               # 15s Standard-Intervall
        # keine externen Assets / kein CDN
        self.assertNotIn("http://", body.replace("http://127.0.0.1", ""))
        self.assertNotIn("https://", body.replace(
            'lang="de"', "").replace("<!doctype html>", ""))
        self.assertNotIn("cdn", body.lower())

    def test_api_board_same_source_as_bridge_board(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.make_task("BRIDGE-0902", "RUNNING")
        self.make_task("BRIDGE-0903", "ARCHIVED")
        self.start()
        code, body = self.get("/api/board")
        self.assertEqual(code, 200)
        data = json.loads(body)

        rows = _board_rows(self.store)
        self.assertEqual([r["bridge_task_id"] for r in data["board"]],
                         [r[0] for r in rows])
        self.assertEqual(data["board"][0]["projekt"], rows[0][1])
        self.assertEqual(data["board"][0]["richtung"], rows[0][3])
        self.assertEqual(data["board"][0]["status"], "WAITING_FOR_COPY_TO_CONTROL")

        other_ids = [r["bridge_task_id"] for r in data["other"]]
        self.assertIn("BRIDGE-0902", other_ids)       # RUNNING -> Zusatzliste
        self.assertNotIn("BRIDGE-0901", other_ids)    # schon im Board
        self.assertNotIn("BRIDGE-0903", other_ids)    # ARCHIVED ausgeblendet
        self.assertEqual(data["other"][0]["status"], "RUNNING")

    def test_api_board_empty_store(self):
        self.start()
        code, body = self.get("/api/board")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {"board": [], "other": []})

    def test_no_write_access_in_run01(self):
        self.start()
        self.assertEqual(self.request("POST", "/api/board")[0], 405)
        self.assertEqual(self.request("DELETE", "/api/task/BRIDGE-0901/archive")[0], 405)
        self.assertEqual(self.get("/api/task/BRIDGE-0901/copied")[0], 404)
        self.assertEqual(self.get("/nonsense")[0], 404)

    def test_broken_store_returns_json_500_and_server_survives(self):
        self.start()
        orig = webui.board_payload
        webui.board_payload = lambda store: (_ for _ in ()).throw(RuntimeError("kaputt"))
        try:
            code, body = self.get("/api/board")
        finally:
            webui.board_payload = orig
        self.assertEqual(code, 500)
        self.assertEqual(json.loads(body)["error"], "kaputt")
        # Server lebt weiter
        self.assertEqual(self.get("/api/board")[0], 200)

    def test_serve_binds_only_localhost(self):
        self.start()
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")


class WebUiCliTests(WebUiBase):
    def test_serve_subcommand_reports_bind_error_cleanly(self):
        import bridge.webui as wu
        orig = wu.serve

        def boom(*a, **kw):
            raise OSError("[Errno 98] Address already in use")

        wu.serve = boom
        try:
            code, _, err = self.cli("webui", "serve", "--actor", "x", "--port", "8420")
        finally:
            wu.serve = orig
        self.assertEqual(code, 1)
        self.assertIn("8420", err)
        self.assertNotIn("Traceback", err)

    def test_serve_subcommand_ctrl_c_exits_clean(self):
        import bridge.webui as wu
        orig = wu.serve

        class _Fake:
            server_address = ("127.0.0.1", 8420)

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                self.closed = True

        fake = _Fake()
        wu.serve = lambda *a, **kw: fake
        try:
            code, out, err = self.cli("webui", "serve", "--actor", "x")
        finally:
            wu.serve = orig
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", err)
        self.assertTrue(getattr(fake, "closed", False))
        self.assertIn("127.0.0.1:8420", out)

    def test_serve_subcommand_requires_actor(self):
        code, _, _ = self.cli("webui", "serve")
        self.assertEqual(code, 2)

    def test_no_host_flag_exposed(self):
        code, out, err = self.cli("webui", "serve", "--host", "0.0.0.0", "--actor", "x")
        self.assertEqual(code, 2)  # unbekanntes Flag -> Nutzungsfehler


if __name__ == "__main__":
    unittest.main()
