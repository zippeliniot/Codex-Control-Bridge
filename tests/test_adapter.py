"""Hermetische Tests für den Read-only-Adapter (BRIDGE-011). stdlib unittest.

Baut ein synthetisches Wegwerf-Git-Repo im Temp-Verzeichnis als "fremdes"
Projekt (Dorfschaft-Stand-in). KEIN echtes Dorfschaft, kein WSL. Git-Commits
laufen mit -c user.name/-c user.email pro Aufruf, nie mit --global.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from bridge import adapter as adapter_mod  # noqa: E402
from bridge import importer  # noqa: E402
from bridge.store import Store  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"
TS = "2026-01-01T00:00:00Z"


def _run_git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True, text=True)


def _git_out(repo, *args) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def _commit(repo, message):
    _run_git(repo, "-c", "user.email=test@example.com", "-c", "user.name=Test",
             "commit", "-m", message)


def make_foreign_repo(base) -> Path:
    """Synthetisches Wegwerf-Git-Repo als Stand-in für ein fremdes Projekt."""
    repo = base / "dorfschaft"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    (repo / "a.txt").write_text("A\n", encoding="utf-8")
    _run_git(repo, "add", "a.txt")
    _commit(repo, "erster commit")
    (repo / "b.txt").write_text("B\n", encoding="utf-8")
    _run_git(repo, "add", "b.txt")
    _commit(repo, "zweiter commit")
    return repo


def ro_profile(**over):
    doc = {
        "schema_version": "1.0", "kind": "bridge_project_profile",
        "project_id": "dorfschaft", "repository": "Dorfschaft",
        "default_branch": "main", "task_prefix": "DORF", "read_only": True,
    }
    doc.update(over)
    return doc


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


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-adapter-"))
        self.repo = make_foreign_repo(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class GitInfoTests(Base):
    def test_git_info_matches_real_git(self):
        a = adapter_mod.ReadOnlyProjectAdapter(ro_profile(), self.repo,
                                               schema_dir=SCHEMA_DIR)
        info = a.git_info()
        self.assertEqual(info["head"], _git_out(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(info["branch"],
                         _git_out(self.repo, "rev-parse", "--abbrev-ref", "HEAD"))
        self.assertEqual(info["repository"], "dorfschaft")
        self.assertIn("b.txt", info["changed_files"])

    def test_git_info_with_base_head_lists_commits(self):
        root_commit = _git_out(self.repo, "rev-list", "--max-parents=0", "HEAD")
        a = adapter_mod.ReadOnlyProjectAdapter(ro_profile(), self.repo,
                                               schema_dir=SCHEMA_DIR)
        info = a.git_info(base_head=root_commit)
        self.assertEqual(info["base_head"], root_commit)
        self.assertEqual(len(info["commits"]), 1)
        self.assertIn("b.txt", info["changed_files"])


class WriteRejectionTests(Base):
    def test_write_command_rejected_repo_unchanged(self):
        allowlist = adapter_mod.load_allowlist(SCHEMA_DIR)
        head_before = _git_out(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(adapter_mod.ReadOnlyViolation):
            adapter_mod.run_readonly_git(self.repo, ["commit", "-m", "boese"],
                                         allowlist=allowlist)
        self.assertEqual(_git_out(self.repo, "rev-parse", "HEAD"), head_before)

    def test_other_write_commands_rejected(self):
        allowlist = adapter_mod.load_allowlist(SCHEMA_DIR)
        head_before = _git_out(self.repo, "rev-parse", "HEAD")
        for cmd in (["push"], ["checkout", "-b", "x"],
                   ["reset", "--hard"], ["add", "."]):
            with self.assertRaises(adapter_mod.ReadOnlyViolation):
                adapter_mod.run_readonly_git(self.repo, cmd, allowlist=allowlist)
        self.assertEqual(_git_out(self.repo, "rev-parse", "HEAD"), head_before)


class ProfileGuardTests(Base):
    def test_non_readonly_profile_rejected(self):
        with self.assertRaises(adapter_mod.ReadOnlyViolation):
            adapter_mod.ReadOnlyProjectAdapter(
                ro_profile(read_only=False), self.repo, schema_dir=SCHEMA_DIR)


class AllowlistTests(unittest.TestCase):
    def test_allowlist_loaded_from_yaml_not_hardcoded(self):
        allowlist = adapter_mod.load_allowlist(SCHEMA_DIR)
        self.assertIn("log", allowlist)
        self.assertNotIn("commit", allowlist)
        doc = yaml.safe_load(
            (SCHEMA_DIR / "git-readonly-allowlist.yaml").read_text(encoding="utf-8"))
        self.assertEqual(allowlist, set(doc["allowed_git_subcommands"]))


class IntegrationTests(Base):
    def test_as_git_info_fn_feeds_importer_into_ccb_store(self):
        ccb_root = Path(tempfile.mkdtemp(prefix="ccb-store-"))
        self.addCleanup(shutil.rmtree, ccb_root, ignore_errors=True)
        for name in ("tasks", "results", "audit"):
            (ccb_root / name).mkdir()
        store = Store(root=ccb_root, schema_dir=SCHEMA_DIR)
        store.create_task(valid_task())

        a = adapter_mod.ReadOnlyProjectAdapter(ro_profile(), self.repo,
                                               schema_dir=SCHEMA_DIR)
        head_before = _git_out(self.repo, "rev-parse", "HEAD")

        result = importer.import_result(
            store, "BRIDGE-900", "COMPLETED",
            draft={"summary": "Dorfschaft-Stand read-only gelesen."},
            git_info_fn=a.as_git_info_fn(),
        )

        self.assertEqual(result["repository"], "dorfschaft")
        self.assertEqual(result["head"], head_before)
        path = ccb_root / "results" / "BRIDGE-900" / "RUN-01" / "result.yaml"
        self.assertTrue(path.exists())
        store.validate(result)
        # fremdes Repo bleibt unveraendert
        self.assertEqual(_git_out(self.repo, "rev-parse", "HEAD"), head_before)


if __name__ == "__main__":
    unittest.main()
