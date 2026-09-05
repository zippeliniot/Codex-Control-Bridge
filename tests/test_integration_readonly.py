"""Hermetischer Test des Read-only-Integrationstests (BRIDGE-012). stdlib unittest.

Führt denselben Ablauf wie scripts/integration_readonly.py gegen ein
synthetisches Wegwerf-Git-Repo aus - unabhängig vom echten CCB-Git-Stand.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import yaml  # noqa: E402

import integration_readonly as intgr  # noqa: E402
from bridge import adapter  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"


def _run_git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True, text=True)


def _git_out(repo, *args) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def _commit(repo, msg):
    _run_git(repo, "-c", "user.email=test@example.com", "-c", "user.name=Test",
             "commit", "-m", msg)


def make_target_repo(base) -> Path:
    repo = base / "target"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    (repo / "a.txt").write_text("A\n", encoding="utf-8")
    _run_git(repo, "add", "a.txt")
    _commit(repo, "erster commit")
    (repo / "b.txt").write_text("B\n", encoding="utf-8")
    _run_git(repo, "add", "b.txt")
    _commit(repo, "zweiter commit")
    return repo


class IntegrationReadonlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-int-"))
        self.repo = make_target_repo(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_observation_leaves_target_unchanged(self):
        head_before = _git_out(self.repo, "rev-parse", "HEAD")
        out = self.tmp / "store-out"
        report = intgr.run(self.repo, out, SCHEMA_DIR)

        self.assertTrue(report["passed"], report["checks"])
        self.assertEqual(_git_out(self.repo, "rev-parse", "HEAD"), head_before)
        self.assertEqual(_git_out(self.repo, "status", "--porcelain"), "")

        rp = report["result_path"]
        self.assertTrue(rp.is_file())
        self.assertIn(out.resolve(), rp.resolve().parents)
        doc = yaml.safe_load(rp.read_text(encoding="utf-8"))
        self.assertEqual(doc["head"], head_before)
        self.assertEqual(doc["repository"], self.repo.name)

        # kein Schreibzugriff aufs Zielrepo
        self.assertFalse((self.repo / "tasks").exists())
        self.assertFalse((self.repo / "results").exists())
        self.assertFalse((self.repo / "audit").exists())

    def test_out_inside_target_is_rejected(self):
        with self.assertRaises(RuntimeError):
            intgr.run(self.repo, self.repo / "sub-out", SCHEMA_DIR)

    def test_write_attempt_via_adapter_is_rejected(self):
        ro = adapter.ReadOnlyProjectAdapter({"read_only": True}, self.repo,
                                            schema_dir=SCHEMA_DIR)
        head_before = _git_out(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(adapter.ReadOnlyViolation):
            adapter.run_readonly_git(self.repo,
                                     ["commit", "--allow-empty", "-m", "x"],
                                     allowlist=ro.allowlist)
        self.assertEqual(_git_out(self.repo, "rev-parse", "HEAD"), head_before)

    def test_main_pass_exit_zero(self):
        code = intgr.main(["--target", str(self.repo),
                           "--out", str(self.tmp / "o2"),
                           "--schema-dir", str(SCHEMA_DIR)])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
