"""Hermetische Tests fuer die Web-UI (BRIDGE-020, RUN-01 lesend + RUN-02 Aktionen).

Startet einen echten Server auf einem vom OS vergebenen Port (0), ruft ihn per
``urllib.request`` ab und faehrt ihn wieder herunter - kein Mock der HTTP-Schicht.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from bridge import importer, webui  # noqa: E402
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

    _SENTINEL = object()

    def post_json(self, path, body, *, origin=_SENTINEL):
        port = self.httpd.server_address[1]
        headers = {"Content-Type": "application/json"}
        if origin is self._SENTINEL:
            origin = f"http://127.0.0.1:{port}"
        if origin is not None:
            headers["Origin"] = origin
        data = b"" if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, json.loads(res.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}")

    def status_of(self, task_id):
        return self.store.load_task(task_id).get("status")

    def audit_lines(self):
        f = self.tmp / "audit" / "audit.jsonl"
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


# 'task create' laesst den Auftrag bereits in WAITING_FOR_HANDOFF_TO_EXECUTOR.
_WALK = {
    None: [],
    "WAITING_FOR_HANDOFF_TO_EXECUTOR": [],
    "RUNNING": ["CLAIMED", "RUNNING"],
    "WAITING_FOR_COPY_TO_CONTROL": ["CLAIMED", "RUNNING", "COMPLETED",
                                    "WAITING_FOR_COPY_TO_CONTROL"],
    "REVIEW_REQUIRED": ["CLAIMED", "RUNNING", "COMPLETED",
                        "WAITING_FOR_COPY_TO_CONTROL", "REVIEW_REQUIRED"],
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
        data = json.loads(body)
        self.assertEqual(data["board"], [])
        self.assertEqual(data["other"], [])
        self.assertEqual(data["actor"], "tester")   # Vorbelegung fuer Buttons

    def test_unknown_routes_and_methods(self):
        self.start()
        self.assertEqual(self.request("POST", "/api/board")[0], 404)   # kein POST-Ziel
        self.assertEqual(self.request("PUT", "/api/task/BRIDGE-0901/archive")[0], 405)

    # -- /api/overview (BRIDGE-026) ----------------------------

    def test_api_overview_returns_all_statuses_incl_running(self):
        """overview zeigt RUNNING/CLAIMED (die das Board verbirgt) - Abgrenzungstest."""
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.make_task("BRIDGE-0902", "RUNNING")
        self.make_task("BRIDGE-0903", "ARCHIVED")
        self.start()
        code, body = self.get("/api/overview")
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertIn("overview", data)
        self.assertIn("inactive_threshold_minutes", data)
        ids = [r["bridge_task_id"] for r in data["overview"]]
        # Alle drei Auftraege muessen erscheinen (kein Zustandsfilter)
        self.assertIn("BRIDGE-0901", ids)
        self.assertIn("BRIDGE-0902", ids)
        self.assertIn("BRIDGE-0903", ids)

    def test_api_overview_running_not_in_board_but_in_overview(self):
        """RUNNING erscheint in /api/overview, nicht im board-Bereich von /api/board."""
        self.make_task("BRIDGE-0901", "RUNNING")
        self.start()
        # board verbirgt RUNNING
        _, board_body = self.get("/api/board")
        board_data = json.loads(board_body)
        board_ids = [r["bridge_task_id"] for r in board_data["board"]]
        self.assertNotIn("BRIDGE-0901", board_ids)
        # overview zeigt RUNNING
        _, ov_body = self.get("/api/overview")
        ov_data = json.loads(ov_body)
        ov_ids = [r["bridge_task_id"] for r in ov_data["overview"]]
        self.assertIn("BRIDGE-0901", ov_ids)

    def test_api_overview_missing_machine_is_question_mark(self):
        """Fehlendes machine-Feld -> '?' (kein Erfinden von Werten)."""
        self.make_task("BRIDGE-0901")
        self.start()
        _, body = self.get("/api/overview")
        data = json.loads(body)
        row = next(r for r in data["overview"] if r["bridge_task_id"] == "BRIDGE-0901")
        self.assertEqual(row["machine"], "?")

    def test_api_overview_active_task_is_active_flag_true(self):
        """RUNNING mit frischem Heartbeat -> is_active=True in API-Antwort."""
        import json as _json
        from datetime import datetime, timezone
        self.make_task("BRIDGE-0901", "RUNNING")
        hb_dir = self.tmp / "results" / "BRIDGE-0901" / "RUN-01"
        hb_dir.mkdir(parents=True, exist_ok=True)
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (hb_dir / "heartbeat.json").write_text(_json.dumps({
            "kind": "bridge_heartbeat", "bridge_task_id": "BRIDGE-0901",
            "run_id": "RUN-01", "last_seen": now_ts,
        }), encoding="utf-8")
        self.start()
        _, body = self.get("/api/overview")
        data = _json.loads(body)
        row = next(r for r in data["overview"] if r["bridge_task_id"] == "BRIDGE-0901")
        self.assertTrue(row["is_active"])

    def test_page_html_contains_overview_section(self):
        """Die HTML-Seite enthaelt die Gesamtuebersicht-Tabelle (kein separater GET noetig)."""
        self.start()
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("ov-table", body)
        self.assertIn("/api/overview", body)
        self.assertIn("renderOverview", body)
        self.assertIn("lastOverviewData", body)
        self.assertEqual(self.request("DELETE", "/api/task/BRIDGE-0901/archive")[0], 405)
        self.assertEqual(self.get("/api/task/BRIDGE-0901/copied")[0], 404)  # GET auf POST-Ziel
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

    # -- /api/overview priority field (BRIDGE-028) -----------------

    def test_api_overview_includes_priority_field(self):
        """overview-Payload enthaelt priority-Feld pro Zeile (BRIDGE-028)."""
        path = self.tmp / "BRIDGE-0901.yaml"
        path.write_text(yaml.safe_dump(task_doc(
            bridge_task_id="BRIDGE-0901", priority="HIGH")), encoding="utf-8")
        self.cli("task", "create", str(path))
        self.start()
        code, body = self.get("/api/overview")
        self.assertEqual(code, 200)
        data = json.loads(body)
        row = next(r for r in data["overview"] if r["bridge_task_id"] == "BRIDGE-0901")
        self.assertEqual(row["priority"], "HIGH")

    def test_api_overview_missing_priority_defaults_to_medium(self):
        """Auftraege ohne priority-Feld liefern MEDIUM als Default im overview-Payload."""
        self.make_task("BRIDGE-0901")   # kein priority-Feld
        self.start()
        code, body = self.get("/api/overview")
        data = json.loads(body)
        row = next(r for r in data["overview"] if r["bridge_task_id"] == "BRIDGE-0901")
        self.assertEqual(row["priority"], "MEDIUM")

    def test_api_board_includes_priority_field(self):
        """board-Payload enthaelt priority-Feld (BRIDGE-028)."""
        path = self.tmp / "BRIDGE-0901.yaml"
        path.write_text(yaml.safe_dump(task_doc(
            bridge_task_id="BRIDGE-0901", priority="LOW")), encoding="utf-8")
        self.cli("task", "create", str(path))
        self.start()
        code, body = self.get("/api/board")
        data = json.loads(body)
        row = data["board"][0]
        self.assertEqual(row["priority"], "LOW")

    def test_page_html_contains_priority_select(self):
        """HTML der Web-UI enthaelt einen <select> fuer Prioritaets-Zuweisung."""
        self.start()
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("data-prio-id", body)   # JS-Attribut fuer <select>

    def test_page_html_contains_priority_column_header(self):
        """HTML der Web-UI enthaelt eine Prio-Spaltenüberschrift in den Tabellen."""
        self.start()
        code, body = self.get("/")
        self.assertIn("Prio", body)


class WebUiActionTests(WebUiBase):
    """RUN-02: POST-Endpunkte task copied / archive / run finish."""

    def _git_stub(self, root=None, base_head=None):
        return {"repository": "R", "branch": "b", "head": "a" * 40,
                "base_head": base_head, "commits": [], "changed_files": []}

    # -- Same-Origin ----------------------------------------------

    def test_post_without_origin_or_referer_is_403(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/copied",
                                    {"actor": "h", "confirm": True}, origin=None)
        self.assertEqual(code, 403)
        self.assertEqual(self.status_of("BRIDGE-0901"), "WAITING_FOR_COPY_TO_CONTROL")

    def test_post_with_foreign_origin_is_403(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.start()
        code, _ = self.post_json("/api/task/BRIDGE-0901/copied",
                                 {"actor": "h", "confirm": True},
                                 origin="http://evil.example")
        self.assertEqual(code, 403)
        self.assertEqual(self.status_of("BRIDGE-0901"), "WAITING_FOR_COPY_TO_CONTROL")

    # -- Bestaetigungspflicht -----------------------------------

    def test_copied_without_confirm_is_400(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.start()
        code, _ = self.post_json("/api/task/BRIDGE-0901/copied", {"actor": "h"})
        self.assertEqual(code, 400)
        self.assertEqual(self.status_of("BRIDGE-0901"), "WAITING_FOR_COPY_TO_CONTROL")

    def test_copied_without_actor_is_400(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.start()
        code, _ = self.post_json("/api/task/BRIDGE-0901/copied",
                                 {"actor": "   ", "confirm": True})
        self.assertEqual(code, 400)

    # -- Erfolg + echte Zustandsaenderung (Integration) ----------

    def test_copied_success_changes_state_and_audit(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/copied",
                                    {"actor": "human", "confirm": True})
        self.assertEqual(code, 200)
        self.assertEqual(data["new_state"], "REVIEW_REQUIRED")
        # echte Aenderung, nicht nur HTTP 200:
        self.assertEqual(self.status_of("BRIDGE-0901"), "REVIEW_REQUIRED")
        board = json.loads(self.get("/api/board")[1])
        self.assertNotIn("BRIDGE-0901",
                         [r["bridge_task_id"] for r in board["board"]])
        # Audit-Eintrag durch die echte Store-Logik, mit actor:
        last = self.audit_lines()[-1]
        self.assertEqual(last["event_type"], "REVIEW_REQUESTED")
        self.assertEqual(last["actor"], "human")

    def test_copied_wrong_state_same_error_as_cli(self):
        self.make_task("BRIDGE-0901", "RUNNING")
        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/copied",
                                    {"actor": "h", "confirm": True})
        self.assertEqual(code, 409)
        self.assertIn("WAITING_FOR_COPY_TO_CONTROL", data["error"])
        self.assertEqual(self.status_of("BRIDGE-0901"), "RUNNING")

    def test_archive_success(self):
        self.make_task("BRIDGE-0901", "REVIEW_REQUIRED")
        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/archive",
                                    {"actor": "human", "confirm": True,
                                     "reason": "fertig"})
        self.assertEqual(code, 200)
        self.assertEqual(self.status_of("BRIDGE-0901"), "ARCHIVED")

    def test_finish_success_auto_chains_and_writes_result(self):
        self.make_task("BRIDGE-0901")                 # -> WAITING_FOR_HANDOFF
        self.cli("run", "start", "BRIDGE-0901", "--actor", "x")   # -> RUNNING + Heartbeat
        self.start()
        with mock.patch.object(importer, "collect_git_info", self._git_stub):
            code, data = self.post_json(
                "/api/run/BRIDGE-0901/finish",
                {"actor": "human", "confirm": True, "status": "COMPLETED",
                 "summary": "Web-Abschluss Testlauf"})
        self.assertEqual(code, 200, data)
        self.assertEqual(data["run_id"], "RUN-01")
        # BRIDGE-014 Auto-Chain, exakt wie beim CLI:
        self.assertEqual(self.status_of("BRIDGE-0901"), "WAITING_FOR_COPY_TO_CONTROL")
        self.assertTrue((self.tmp / "results" / "BRIDGE-0901" / "RUN-01"
                         / "result.yaml").exists())

    def test_finish_without_summary_is_400(self):
        self.make_task("BRIDGE-0901", "RUNNING")
        self.start()
        code, _ = self.post_json("/api/run/BRIDGE-0901/finish",
                                 {"actor": "h", "confirm": True,
                                  "status": "COMPLETED", "summary": "  "})
        self.assertEqual(code, 400)
        self.assertEqual(self.status_of("BRIDGE-0901"), "RUNNING")

    def test_finish_disallowed_status_is_409(self):
        self.make_task("BRIDGE-0901", "RUNNING")
        self.start()
        code, data = self.post_json("/api/run/BRIDGE-0901/finish",
                                    {"actor": "h", "confirm": True,
                                     "status": "READY", "summary": "x"})
        self.assertEqual(code, 409)
        self.assertEqual(self.status_of("BRIDGE-0901"), "RUNNING")

    # -- payload: Buttons nur fuer zulaessige Uebergaenge --------

    def test_board_payload_lists_allowed_actions_only(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self.make_task("BRIDGE-0902", "RUNNING")
        self.start()
        data = json.loads(self.get("/api/board")[1])
        by_id = {r["bridge_task_id"]: r["actions"]
                 for r in data["board"] + data["other"]}
        # WAITING_FOR_COPY_TO_CONTROL -> REVIEW_REQUIRED (copied) und -> ARCHIVED
        # sind laut state-model.yaml beide erlaubt; kein finish (nicht RUNNING).
        self.assertEqual(by_id["BRIDGE-0901"], ["copied", "archive"])
        # RUNNING -> ARCHIVED ist NICHT erlaubt, nur finish.
        self.assertEqual(by_id["BRIDGE-0902"], ["finish"])

    def test_cli_task_copied_still_works(self):
        # Regression: bestehendes CLI-Verhalten unveraendert.
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        code, out, _ = self.cli("task", "copied", "BRIDGE-0901", "--actor", "h")
        self.assertEqual(code, 0)
        self.assertIn("REVIEW_REQUIRED", out)
        self.assertEqual(self.status_of("BRIDGE-0901"), "REVIEW_REQUIRED")

    # -- POST /api/task/<id>/priority (BRIDGE-028) ----------------

    def test_priority_endpoint_success(self):
        """POST /api/task/<id>/priority aendert das Feld und gibt ok:true zurueck."""
        self.make_task("BRIDGE-0901")
        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/priority",
                                    {"actor": "test", "confirm": True, "priority": "HIGH"})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["event_type"], "PRIORITY_CHANGED")
        # Store-Feld tatsaechlich geaendert
        task = self.store.load_task("BRIDGE-0901")
        self.assertEqual(task["priority"], "HIGH")

    def test_priority_endpoint_writes_audit_entry(self):
        """Nach dem Endpunkt-Aufruf steht PRIORITY_CHANGED in audit.jsonl."""
        self.make_task("BRIDGE-0901")
        self.start()
        self.post_json("/api/task/BRIDGE-0901/priority",
                       {"actor": "test", "confirm": True, "priority": "LOW"})
        types = [e["event_type"] for e in self.audit_lines()]
        self.assertIn("PRIORITY_CHANGED", types)

    def test_priority_endpoint_missing_confirm_is_400(self):
        """Fehlende Bestaetigungspflicht -> HTTP 400."""
        self.make_task("BRIDGE-0901")
        self.start()
        code, _ = self.post_json("/api/task/BRIDGE-0901/priority",
                                 {"actor": "test", "priority": "HIGH"})
        self.assertEqual(code, 400)

    def test_priority_endpoint_missing_actor_is_400(self):
        """Fehlender actor -> HTTP 400."""
        self.make_task("BRIDGE-0901")
        self.start()
        code, _ = self.post_json("/api/task/BRIDGE-0901/priority",
                                 {"actor": "   ", "confirm": True, "priority": "HIGH"})
        self.assertEqual(code, 400)

    def test_priority_endpoint_invalid_value_is_400(self):
        """Ungueltiger Prioritaetswert -> HTTP 400."""
        self.make_task("BRIDGE-0901")
        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/priority",
                                    {"actor": "test", "confirm": True, "priority": "URGENT"})
        self.assertEqual(code, 400)
        # Kein stilles Ignorieren: Store unveraendert
        task = self.store.load_task("BRIDGE-0901")
        self.assertNotIn("priority", task)

    def test_priority_endpoint_same_store_as_cli(self):
        """Web-UI-Endpunkt und CLI nutzen dieselbe Store-Methode (kein Parallel-Code)."""
        self.make_task("BRIDGE-0901")
        self.start()
        # CLI setzt auf HIGH
        self.cli("task", "set-priority", "BRIDGE-0901", "HIGH", "--actor", "cli")
        task_cli = self.store.load_task("BRIDGE-0901")
        # Web-UI setzt auf LOW
        self.post_json("/api/task/BRIDGE-0901/priority",
                       {"actor": "webui", "confirm": True, "priority": "LOW"})
        task_webui = self.store.load_task("BRIDGE-0901")
        # Beide haben das gleiche Feld beschrieben
        self.assertEqual(task_cli["priority"], "HIGH")
        self.assertEqual(task_webui["priority"], "LOW")


_NODE = shutil.which("node")


def _run_node(script: str) -> str:
    proc = subprocess.run([_NODE, "-e", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=20)
    if proc.returncode != 0:
        raise AssertionError(f"node fehlgeschlagen: {proc.stderr or proc.stdout}")
    return proc.stdout.strip()


class WebUiFrontendTests(unittest.TestCase):
    """BRIDGE-023: Auto-Refresh-Härtung, persistenter Log, Client-Filter.

    Reines Frontend-JS in ``_PAGE`` - getestet über (a) strukturelle Zusicherungen
    am Template und (b) die als ``webui._PURE_JS`` isolierten seiteneffektfreien
    Funktionen, ausgeführt per node (übersprungen, wenn node fehlt).
    """

    PAGE = webui._PAGE
    SCRIPT = re.search(r"<script>(.*)</script>", webui._PAGE, re.S).group(1)

    # -- Struktur / Regression ------------------------------------

    def test_flash_and_log_both_present(self):
        # #flash bleibt, #log kommt zusaetzlich dazu (kein Ersatz).
        self.assertIn('<div id="flash">', self.PAGE)
        self.assertIn('<div id="log"', self.PAGE)
        self.assertIn("overflow-y: auto", self.PAGE)  # scrollbarer Log

    def test_actor_field_not_overwritten_when_filled(self):
        # Regression (Akzeptanzkriterium 1): refresh() befuellt actor nur, wenn leer.
        self.assertRegex(self.SCRIPT, r"if\s*\(\s*!actorInput\.value\b")

    def test_filter_inputs_present_and_static(self):
        for fid in ("f-projekt", "f-status", "f-id"):
            self.assertEqual(self.PAGE.count(f'id="{fid}"'), 1,
                             f"{fid} muss genau einmal (statisch im HTML) stehen")
        self.assertIn('id="f-clear"', self.PAGE)

    def test_log_is_appended_from_post_not_refresh(self):
        # addLog() wird in post() aufgerufen (Erfolg UND Fehler), nie in refresh().
        post_body = re.search(r"async function post\(.*?\n\}\n", self.SCRIPT, re.S).group(0)
        refresh_body = re.search(r"async function refresh\(.*?\n\}\n", self.SCRIPT, re.S).group(0)
        self.assertGreaterEqual(post_body.count("addLog("), 3)   # ok + http-err + net-err
        self.assertNotIn("addLog(", refresh_body)

    def test_refresh_only_touches_tbody_not_filter_inputs(self):
        refresh_body = re.search(r"async function refresh\(.*?\n\}\n", self.SCRIPT, re.S).group(0)
        # refresh() rendert ueber renderTables(); baut die Inputs nicht neu.
        self.assertIn("renderTables()", refresh_body)
        for fid in ("f-projekt", "f-status", "f-id"):
            self.assertNotIn(fid, refresh_body)

    def test_filter_state_kept_in_js_variable(self):
        self.assertRegex(self.SCRIPT, r"const filterState\s*=\s*\{")
        # renderTables liest filterState (nicht die DOM-Werte direkt)
        render = re.search(r"function renderTables\(.*?\n\}\n", self.SCRIPT, re.S).group(0)
        self.assertIn("filterState", render)

    def test_no_new_server_route(self):
        # POST-Routen: task und run (BRIDGE-028 fuegt priority hinzu, run unveraendert).
        self.assertEqual(set(webui._Handler._POST_ROUTES), {"task", "run"})
        # BRIDGE-028: priority-Route hinzugefuegt (kein Git-Commit/Push, nur Store-Feld)
        self.assertIn("copied", webui._Handler._POST_ROUTES["task"])
        self.assertIn("archive", webui._Handler._POST_ROUTES["task"])
        self.assertIn("priority", webui._Handler._POST_ROUTES["task"])
        self.assertEqual(webui._Handler._POST_ROUTES["run"], {"finish": "finish"})

    # -- seiteneffektfreie Logik per node ------------------------

    @unittest.skipUnless(_NODE, "node nicht verfügbar")
    def test_filter_rows_projekt_status_id_and_combined(self):
        script = webui._PURE_JS + textwrap.dedent("""
            const rows = [
              {bridge_task_id: "BRIDGE-0007", projekt: "DORF", status: "RUNNING"},
              {bridge_task_id: "BRIDGE-0023", projekt: "BRIDGE", status: "RUNNING"},
              {bridge_task_id: "DORF-0100",  projekt: "DORF", status: "REVIEW_REQUIRED"},
            ];
            const ids = f => filterRows(rows, f).map(r => r.bridge_task_id).join(",");
            console.log(JSON.stringify({
              projekt: ids({projekt: "dorf"}),
              status:  ids({status: "review"}),
              id:      ids({id: "0023"}),
              combo:   ids({projekt: "dorf", status: "running"}),
              none:    ids({}),
            }));
        """)
        out = json.loads(_run_node(script))
        self.assertEqual(out["projekt"], "BRIDGE-0007,DORF-0100")
        self.assertEqual(out["status"], "DORF-0100")
        self.assertEqual(out["id"], "BRIDGE-0023")
        self.assertEqual(out["combo"], "BRIDGE-0007")
        self.assertEqual(out["none"], "BRIDGE-0007,BRIDGE-0023,DORF-0100")

    @unittest.skipUnless(_NODE, "node nicht verfügbar")
    def test_make_log_entry_has_four_fields_for_ok_and_error(self):
        script = webui._PURE_JS + textwrap.dedent("""
            const ok  = makeLogEntry("12:00:00", "copied", "BRIDGE-0023", true,  "A -> B");
            const err = makeLogEntry("12:00:01", "finish", "BRIDGE-0023", false, "Fehler 409: x");
            console.log(JSON.stringify({ok, err, okLine: formatLogEntry(ok), errLine: formatLogEntry(err)}));
        """)
        out = json.loads(_run_node(script))
        for e in (out["ok"], out["err"]):
            self.assertEqual(set(e), {"time", "action", "bridge_task_id", "ok", "result"})
        self.assertTrue(out["ok"]["ok"])
        self.assertFalse(out["err"]["ok"])
        self.assertIn("copied BRIDGE-0023: A -> B", out["okLine"])
        self.assertIn("finish BRIDGE-0023: Fehler 409", out["errLine"])

    @unittest.skipUnless(_NODE, "node nicht verfügbar")
    def test_filter_reapplies_to_fresh_data_after_refresh_tick(self):
        # "Filter-Persistenz ueber einen simulierten Refresh-Tick": derselbe
        # filterState, danach neue Daten -> Filter greift erneut, ohne Reset.
        script = webui._PURE_JS + textwrap.dedent("""
            const filterState = {projekt: "dorf", status: "", id: ""};
            let lastData = {board: [], other: [{bridge_task_id: "DORF-1", projekt: "DORF", status: "RUNNING"}]};
            const view = () => filterRows(lastData.other, filterState).map(r => r.bridge_task_id);
            const before = view();
            // Refresh-Tick: neue Daten kommen an, filterState bleibt unangetastet
            lastData = {board: [], other: [
              {bridge_task_id: "DORF-2", projekt: "DORF", status: "RUNNING"},
              {bridge_task_id: "BRIDGE-9", projekt: "BRIDGE", status: "RUNNING"},
            ]};
            console.log(JSON.stringify({before, after: view()}));
        """)
        out = json.loads(_run_node(script))
        self.assertEqual(out["before"], ["DORF-1"])
        self.assertEqual(out["after"], ["DORF-2"])   # Filter weiterhin aktiv


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


class WebUiGitActionTests(WebUiBase):
    """BRIDGE-024: Web-UI fuehrt nach copied/archive/finish selbst git commit+push aus.

    Testaufbau: echtes temporaeres Git-Repo (= Store-Root) plus lokales bare
    Repo als Test-'origin'. Kein github.com-Zugriff in Tests.
    """

    def setUp(self):
        super().setUp()
        self.bare_tmp = Path(tempfile.mkdtemp(prefix="ccb-webui-bare-"))
        self._setup_git_repos()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.bare_tmp, ignore_errors=True)

    # -- Git-Hilfen ---------------------------------------------------------

    def _git(self, *args, cwd=None, check=True):
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.tmp,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} fehlgeschlagen (rc={result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result

    def _commit_count(self, cwd=None):
        r = self._git("log", "--oneline", cwd=cwd or self.tmp, check=False)
        return len([l for l in r.stdout.splitlines() if l.strip()])

    def _last_commit_msg(self, cwd=None):
        r = self._git("log", "-1", "--format=%s", cwd=cwd or self.tmp)
        return r.stdout.strip()

    def _bare_head_sha(self):
        """Gibt den aktuellen HEAD-SHA des bare-Repos zurueck (vollstaendig)."""
        r = subprocess.run(
            ["git", "rev-parse", "main"],
            cwd=self.bare_tmp, capture_output=True, text=True,
            encoding="utf-8", timeout=30,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip()

    def _working_head_sha(self):
        """Gibt den aktuellen HEAD-SHA des Arbeits-Repos zurueck (vollstaendig)."""
        r = self._git("rev-parse", "HEAD")
        return r.stdout.strip()

    def _setup_git_repos(self):
        """Initialisiert self.tmp als Git-Repo und self.bare_tmp als bare origin."""
        self._git("init")
        # Sicherstellen, dass der Branch 'main' heisst (auch auf aelteren Git-Versionen).
        self._git("branch", "-M", "main", check=False)
        self._git("symbolic-ref", "HEAD", "refs/heads/main", check=False)
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "CCB Test")

        # Initialer Commit, damit das Repo gueltig ist (mind. 1 Commit benoetigt).
        gitkeep = self.tmp / ".gitkeep"
        gitkeep.write_text("", encoding="utf-8")
        self._git("add", ".gitkeep")
        self._git("commit", "-m", "Initial commit")

        # Bare-Repo als 'origin' einrichten und initialen Stand pushen.
        self._git("init", "--bare", str(self.bare_tmp))
        self._git("remote", "add", "origin", str(self.bare_tmp))
        self._git("push", "-u", "origin", "main")

    def _git_stub(self, root=None, base_head=None):
        """Stub fuer importer.collect_git_info (kein echter Git-Aufruf im Importer)."""
        return {"repository": "R", "branch": "b", "head": "a" * 40,
                "base_head": base_head, "commits": [], "changed_files": []}

    def _stage_and_push_initial_task(self, task_id):
        """Initialen Task-Stand committen und pushen (vor der Aktion).

        Schliesst die temporaere Staging-YAML-Datei von make_task() in den
        Commit ein, damit sie nicht als unerwartete Aenderung beim
        git-Status auftaucht.
        """
        task_dir = self.tmp / "tasks" / task_id
        audit_file = self.tmp / "audit" / "audit.jsonl"
        # Staging-YAML (von make_task): liegt direkt im Repo-Root.
        staging_yaml = self.tmp / f"{task_id}.yaml"

        paths = []
        if task_dir.exists():
            paths.append(str(task_dir))
        if audit_file.exists():
            paths.append(str(audit_file))
        if staging_yaml.exists():
            paths.append(str(staging_yaml))

        if paths:
            self._git("add", *paths)
        self._git("commit", "--allow-empty", "-m", f"Add {task_id} initial state")
        self._git("push")

    # -- Erfolgspfad --------------------------------------------------------

    def test_copied_commits_and_pushes(self):
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self._stage_and_push_initial_task("BRIDGE-0901")
        bare_sha_before = self._bare_head_sha()

        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/copied",
                                    {"actor": "human", "confirm": True})
        self.assertEqual(code, 200, data)
        self.assertIn("git", data)
        git = data["git"]
        self.assertTrue(git["committed"], git)
        self.assertIsNotNone(git["commit"])
        self.assertTrue(git["pushed"], git)
        self.assertIsNone(git["error"])

        # Bare-Repo muss den neuen Commit enthalten (working HEAD == bare HEAD).
        bare_sha_after = self._bare_head_sha()
        working_sha = self._working_head_sha()
        self.assertEqual(bare_sha_after, working_sha,
                         "Push fehlgeschlagen: bare-Repo hat nicht den neuen Commit")
        self.assertNotEqual(bare_sha_after, bare_sha_before,
                            "Keine Aenderung im bare-Repo erkannt")
        # Commit-Nachricht korrekt.
        msg = self._last_commit_msg()
        self.assertIn("BRIDGE-0901", msg)
        self.assertIn("copied", msg)

    def test_archive_commits_and_pushes(self):
        self.make_task("BRIDGE-0901", "REVIEW_REQUIRED")
        self._stage_and_push_initial_task("BRIDGE-0901")
        bare_sha_before = self._bare_head_sha()

        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/archive",
                                    {"actor": "human", "confirm": True,
                                     "reason": "Test fertig"})
        self.assertEqual(code, 200, data)
        self.assertIn("git", data)
        git = data["git"]
        self.assertTrue(git["committed"], git)
        self.assertTrue(git["pushed"], git)
        self.assertIsNone(git["error"])

        bare_sha_after = self._bare_head_sha()
        working_sha = self._working_head_sha()
        self.assertEqual(bare_sha_after, working_sha)
        self.assertNotEqual(bare_sha_after, bare_sha_before)

    def test_finish_commits_and_pushes(self):
        self.make_task("BRIDGE-0901")
        self.cli("run", "start", "BRIDGE-0901", "--actor", "x")
        self._stage_and_push_initial_task("BRIDGE-0901")
        bare_sha_before = self._bare_head_sha()

        self.start()
        with mock.patch.object(importer, "collect_git_info", self._git_stub):
            code, data = self.post_json(
                "/api/run/BRIDGE-0901/finish",
                {"actor": "human", "confirm": True,
                 "status": "COMPLETED", "summary": "Test-Abschluss"})
        self.assertEqual(code, 200, data)
        self.assertIn("git", data)
        git = data["git"]
        self.assertTrue(git["committed"], git)
        self.assertTrue(git["pushed"], git)
        self.assertIsNone(git["error"])

        bare_sha_after = self._bare_head_sha()
        working_sha = self._working_head_sha()
        self.assertEqual(bare_sha_after, working_sha)
        self.assertNotEqual(bare_sha_after, bare_sha_before)
        msg = self._last_commit_msg()
        self.assertIn("BRIDGE-0901", msg)
        self.assertIn("finish", msg)

    # -- Fail-closed-Fall: unerwartete Datei blockiert Commit ---------------

    def test_fail_closed_unexpected_file_blocks_commit(self):
        """Eine Datei ausserhalb der Whitelist → kein Commit, Store-Aktion trotzdem OK."""
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self._stage_and_push_initial_task("BRIDGE-0901")

        # Unerwartete Datei anlegen (nicht in der Whitelist fuer 'copied').
        unexpected = self.tmp / "unexpected.txt"
        unexpected.write_text("nicht in der whitelist", encoding="utf-8")

        before_local = self._commit_count()

        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/copied",
                                    {"actor": "human", "confirm": True})
        # Store-Aktion hat geklappt (HTTP 200), aber git hat abgebrochen.
        self.assertEqual(code, 200, data)
        self.assertIn("git", data)
        git = data["git"]
        self.assertFalse(git["committed"], git)
        self.assertFalse(git["pushed"], git)
        self.assertIsNotNone(git["error"])
        # Fehlertext muss unerwartete Datei nennen.
        self.assertIn("unexpected.txt", git["error"])

        # Kein neuer Commit darf entstanden sein (per git log verifiziert).
        after_local = self._commit_count()
        self.assertEqual(after_local, before_local,
                         "Kein Commit erlaubt, wenn Whitelist-Pruefung schlaegt fehl")

    # -- Push-Fehlschlag: Commit lokal vorhanden, aber nicht gepusht --------

    def test_push_failure_commit_stays_local(self):
        """Divergiertes bare-Repo → Commit bleibt lokal, pushed=false, kein Crash."""
        self.make_task("BRIDGE-0901", "WAITING_FOR_COPY_TO_CONTROL")
        self._stage_and_push_initial_task("BRIDGE-0901")

        # Push-Fehlschlag erzwingen: origin-Remote-URL auf nicht-existierenden Pfad setzen.
        # git push wird dann mit "repository not found" oder aehnlichem fehlschlagen.
        # Das genuegt laut Spec ('z. B. non-fast-forward') fuer den Test.
        self._git("remote", "set-url", "origin", "/nonexistent/path/to/nowhere")

        local_before = self._commit_count()

        self.start()
        code, data = self.post_json("/api/task/BRIDGE-0901/copied",
                                    {"actor": "human", "confirm": True})
        self.assertEqual(code, 200, data)
        self.assertIn("git", data)
        git = data["git"]
        # Commit ist lokal entstanden, Push hat fehlgeschlagen.
        self.assertTrue(git["committed"], git)
        self.assertIsNotNone(git["commit"])
        self.assertFalse(git["pushed"], git)
        self.assertIsNotNone(git["error"])
        # Fehlertext nennt den Push-Fehler.
        self.assertIn("push", git["error"].lower())

        # Lokaler Commit ist vorhanden (eine mehr als davor),
        # kein Crash, kein automatischer Retry.
        local_after = self._commit_count()
        self.assertEqual(local_after, local_before + 1)


if __name__ == "__main__":
    unittest.main()
