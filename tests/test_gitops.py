"""Tests fuer src/bridge/gitops.py (BRIDGE-025).

Prueft:
- expected_git_files: korrekte Whitelist pro kind
- matches_whitelist: exakter und Praefix-Match
- git_commit: Branch-Check, Whitelist-Pruefung, kein --force,
              push=False committet lokal ohne Remote, push=True pusht
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(REPO_ROOT / "src"))

from bridge import gitops


def _git(*args, cwd):
    """Fuehrt ein git-Kommando aus und gibt stdout zurueck (dekodiert)."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} fehlgeschlagen: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _setup_git_repo(tmp: Path):
    """Initialisiert ein Minimal-Git-Repo mit einem initialen Commit."""
    _git("init", "-b", "main", cwd=tmp)
    _git("config", "user.email", "test@example.com", cwd=tmp)
    _git("config", "user.name", "Test", cwd=tmp)
    (tmp / "README.md").write_text("init\n", encoding="utf-8")
    _git("add", "README.md", cwd=tmp)
    _git("commit", "-m", "initial", cwd=tmp)


# --------------------------------------------------------------------------- #
# expected_git_files
# --------------------------------------------------------------------------- #

class ExpectedGitFilesTests(unittest.TestCase):
    """Whitelist-Pfade pro kind korrekt."""

    def test_task_create(self):
        files = gitops.expected_git_files("task_create", "BRIDGE-0001")
        self.assertIn("tasks/BRIDGE-0001/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)

    def test_run_start_includes_heartbeat_dir(self):
        files = gitops.expected_git_files("run_start", "BRIDGE-0001", "RUN-01")
        self.assertIn("tasks/BRIDGE-0001/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)
        self.assertIn("results/BRIDGE-0001/RUN-01/", files)

    def test_run_start_without_run_id(self):
        files = gitops.expected_git_files("run_start", "BRIDGE-0001")
        # Kein Lauf-Praefix ohne run_id
        self.assertNotIn("results/BRIDGE-0001/None/", files)
        prefixes = [f for f in files if f.startswith("results/")]
        self.assertEqual(prefixes, [])

    def test_run_finish_includes_results_and_workpackage(self):
        files = gitops.expected_git_files("run_finish", "BRIDGE-0001", "RUN-01")
        self.assertIn("tasks/BRIDGE-0001/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)
        self.assertIn("results/BRIDGE-0001/RUN-01/", files)
        self.assertIn("work-packages/BRIDGE-0001.md", files)

    def test_finish_webui_includes_results_and_workpackage(self):
        files = gitops.expected_git_files("finish", "BRIDGE-0001", "RUN-01")
        self.assertIn("results/BRIDGE-0001/RUN-01/", files)
        self.assertIn("work-packages/BRIDGE-0001.md", files)

    def test_task_copied(self):
        files = gitops.expected_git_files("task_copied", "BRIDGE-0002")
        self.assertIn("tasks/BRIDGE-0002/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)
        prefixes = [f for f in files if f.startswith("results/")]
        self.assertEqual(prefixes, [])

    def test_task_archive(self):
        files = gitops.expected_git_files("task_archive", "BRIDGE-0003")
        self.assertIn("tasks/BRIDGE-0003/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)

    def test_copied_webui(self):
        files = gitops.expected_git_files("copied", "BRIDGE-0004")
        self.assertIn("tasks/BRIDGE-0004/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)
        prefixes = [f for f in files if f.startswith("results/")]
        self.assertEqual(prefixes, [])

    def test_archive_webui(self):
        files = gitops.expected_git_files("archive", "BRIDGE-0005")
        self.assertIn("tasks/BRIDGE-0005/task.yaml", files)
        self.assertIn("audit/audit.jsonl", files)


# --------------------------------------------------------------------------- #
# matches_whitelist
# --------------------------------------------------------------------------- #

class MatchesWhitelistTests(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(gitops.matches_whitelist(
            "tasks/BRIDGE-0001/task.yaml",
            ["tasks/BRIDGE-0001/task.yaml", "audit/audit.jsonl"],
        ))

    def test_exact_no_match(self):
        self.assertFalse(gitops.matches_whitelist(
            "tasks/BRIDGE-0001/task.yaml",
            ["audit/audit.jsonl"],
        ))

    def test_prefix_match(self):
        self.assertTrue(gitops.matches_whitelist(
            "results/BRIDGE-0001/RUN-01/result.yaml",
            ["results/BRIDGE-0001/RUN-01/"],
        ))

    def test_prefix_no_match_other_task(self):
        self.assertFalse(gitops.matches_whitelist(
            "results/BRIDGE-0002/RUN-01/result.yaml",
            ["results/BRIDGE-0001/RUN-01/"],
        ))

    def test_partial_name_not_a_prefix_match(self):
        # 'audit/audit.json' ist nicht dasselbe wie 'audit/audit.jsonl'
        self.assertFalse(gitops.matches_whitelist(
            "audit/audit.json",
            ["audit/audit.jsonl"],
        ))


# --------------------------------------------------------------------------- #
# Kein --force im Modul (grep-bar)
# --------------------------------------------------------------------------- #

class NoForcePushTests(unittest.TestCase):
    def test_no_force_in_module_source(self):
        source = Path(gitops.__file__).read_text(encoding="utf-8")
        self.assertNotIn("--force", source)
        self.assertNotIn("--force-with-lease", source)


# --------------------------------------------------------------------------- #
# git_commit: Branch-Check, Whitelist, push=False/True
# --------------------------------------------------------------------------- #

class GitCommitTests(unittest.TestCase):
    """Prueft git_commit mit echten Git-Repos (kein Netzwerkzugriff)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-gitops-"))
        self.bare = Path(tempfile.mkdtemp(prefix="ccb-gitops-bare-"))
        _setup_git_repo(self.tmp)
        # bare-Repo als lokaler 'origin' (kein github.com in Tests)
        _git("clone", "--bare", str(self.tmp), str(self.bare), cwd=self.tmp)
        _git("remote", "add", "origin", str(self.bare), cwd=self.tmp)
        _git("push", "--set-upstream", "origin", "main", cwd=self.tmp)
        # Store-Struktur anlegen
        for sub in ("tasks/BRIDGE-0901", "audit", "results/BRIDGE-0901/RUN-01"):
            (self.tmp / sub).mkdir(parents=True, exist_ok=True)
        # Initiale Store-Dateien committen
        (self.tmp / "tasks/BRIDGE-0901/task.yaml").write_text("k: v\n", encoding="utf-8")
        (self.tmp / "audit/audit.jsonl").write_text("", encoding="utf-8")
        _git("add", "tasks/BRIDGE-0901/task.yaml", "audit/audit.jsonl", cwd=self.tmp)
        _git("commit", "-m", "initial store files", cwd=self.tmp)
        _git("push", cwd=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.bare, ignore_errors=True)

    def _head_sha(self, repo=None):
        return _git("rev-parse", "HEAD", cwd=repo or self.tmp)

    def _bare_head_sha(self):
        return _git("rev-parse", "main", cwd=self.bare)

    def _commit_count(self):
        return int(_git("rev-list", "--count", "HEAD", cwd=self.tmp))

    def _touch(self, rel_path: str, content: str = "data\n"):
        p = self.tmp / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # --- Erfolgsfall: push=False (lokal, kein Remote) -----------------------

    def test_push_false_commits_locally_no_push(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "updated\n")
        self._touch("audit/audit.jsonl", "line\n")
        before_bare = self._bare_head_sha()
        count_before = self._commit_count()

        result = gitops.git_commit(self.tmp, "task_create", "BRIDGE-0901",
                                   "test-actor", push=False)

        self.assertTrue(result["committed"], result["error"])
        self.assertIsNotNone(result["commit"])
        self.assertFalse(result["pushed"])
        self.assertIsNone(result["error"])
        # Lokal: ein Commit mehr
        self.assertEqual(self._commit_count(), count_before + 1)
        # Remote unveraendert
        self.assertEqual(self._bare_head_sha(), before_bare)

    # --- Erfolgsfall: push=True (inkl. Remote) ------------------------------

    def test_push_true_commits_and_pushes(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "changed\n")
        self._touch("audit/audit.jsonl", "log\n")
        before_local = self._head_sha()

        result = gitops.git_commit(self.tmp, "task_copied", "BRIDGE-0901",
                                   "test-actor", push=True)

        self.assertTrue(result["committed"], result["error"])
        self.assertTrue(result["pushed"], result["error"])
        self.assertIsNone(result["error"])
        # Bare-Repo sollte den neuen Commit haben
        self.assertNotEqual(self._bare_head_sha(), before_local)
        self.assertEqual(self._bare_head_sha(), self._head_sha())

    # --- run_start mit Heartbeat-Datei --------------------------------------

    def test_run_start_with_heartbeat(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "running\n")
        self._touch("audit/audit.jsonl", "log\n")
        self._touch("results/BRIDGE-0901/RUN-01/heartbeat.json", "{}\n")
        count_before = self._commit_count()

        result = gitops.git_commit(self.tmp, "run_start", "BRIDGE-0901",
                                   "test-actor", run_id="RUN-01", push=False)

        self.assertTrue(result["committed"], result["error"])
        self.assertEqual(self._commit_count(), count_before + 1)

    # --- run_finish mit result.yaml -----------------------------------------

    def test_run_finish_with_result(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "finished\n")
        self._touch("audit/audit.jsonl", "log\n")
        self._touch("results/BRIDGE-0901/RUN-01/result.yaml", "kind: r\n")
        count_before = self._commit_count()

        result = gitops.git_commit(self.tmp, "run_finish", "BRIDGE-0901",
                                   "test-actor", run_id="RUN-01", push=False)

        self.assertTrue(result["committed"], result["error"])
        self.assertEqual(self._commit_count(), count_before + 1)

    # --- Whitelist-Pruefung fail-closed -------------------------------------

    def test_unexpected_file_blocks_commit(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "changed\n")
        self._touch("audit/audit.jsonl", "log\n")
        # Datei ausserhalb der Whitelist
        self._touch("some-unrelated-file.txt", "oops\n")
        count_before = self._commit_count()

        result = gitops.git_commit(self.tmp, "task_archive", "BRIDGE-0901",
                                   "test-actor", push=False)

        self.assertFalse(result["committed"])
        self.assertIsNone(result["commit"])
        self.assertIn("some-unrelated-file.txt", result["error"])
        self.assertIn("Whitelist", result["error"])
        # Kein Commit entstanden
        self.assertEqual(self._commit_count(), count_before)

    # --- Branch-Pruefung fail-closed ----------------------------------------

    def test_wrong_branch_blocks_commit(self):
        _git("checkout", "-b", "feature/test", cwd=self.tmp)
        self._touch("tasks/BRIDGE-0901/task.yaml", "changed\n")

        result = gitops.git_commit(self.tmp, "task_create", "BRIDGE-0901",
                                   "test-actor", push=False)

        self.assertFalse(result["committed"])
        self.assertIn("feature/test", result["error"])
        self.assertIn("main", result["error"])

    # --- Keine Aenderungen ---------------------------------------------------

    def test_no_changes_returns_error_no_commit(self):
        count_before = self._commit_count()
        result = gitops.git_commit(self.tmp, "task_create", "BRIDGE-0901",
                                   "test-actor", push=False)
        self.assertFalse(result["committed"])
        self.assertIn("Keine Aenderungen", result["error"])
        self.assertEqual(self._commit_count(), count_before)

    # --- Push-Fehlschlag: Commit bleibt lokal -------------------------------

    def test_push_failure_commit_stays_local(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "changed\n")
        self._touch("audit/audit.jsonl", "log\n")
        # Remote-URL auf nicht existierenden Pfad setzen -> Push schlaegt fehl
        _git("remote", "set-url", "origin", "/nonexistent/nowhere", cwd=self.tmp)
        count_before = self._commit_count()

        result = gitops.git_commit(self.tmp, "task_create", "BRIDGE-0901",
                                   "test-actor", push=True)

        self.assertTrue(result["committed"])
        self.assertFalse(result["pushed"])
        self.assertIsNotNone(result["error"])
        # Lokaler Commit ist dennoch da
        self.assertEqual(self._commit_count(), count_before + 1)

    # --- Commit-Nachricht enthaelt kind und task_id -------------------------

    def test_commit_message_contains_kind_and_task_id(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "changed\n")
        self._touch("audit/audit.jsonl", "log\n")

        gitops.git_commit(self.tmp, "task_create", "BRIDGE-0901",
                          "test-actor", push=False, source="CLI")

        msg = _git("log", "-1", "--format=%s", cwd=self.tmp)
        self.assertIn("BRIDGE-0901", msg)
        self.assertIn("task_create", msg)
        self.assertIn("CLI", msg)

    # --- Commit-Nachricht enthält Web-UI-Quelle bei source="Web-UI" ---------

    def test_commit_message_webui_source(self):
        self._touch("tasks/BRIDGE-0901/task.yaml", "changed\n")
        self._touch("audit/audit.jsonl", "log\n")

        gitops.git_commit(self.tmp, "copied", "BRIDGE-0901",
                          "test-actor", push=False, source="Web-UI")

        msg = _git("log", "-1", "--format=%s", cwd=self.tmp)
        self.assertIn("Web-UI", msg)


# --------------------------------------------------------------------------- #
# Push-Retry bei Non-Fast-Forward (BRIDGE-029)
# --------------------------------------------------------------------------- #

class GitCommitRetryTests(unittest.TestCase):
    """Prueft den NFF-Retry-Pfad von git_commit() mit echten bare-Repos.

    Infrastruktur identisch zu GitCommitTests (kein doppelter Code):
    - self.tmp  = working clone (der 'eigene' Klon, git_commit laeuft hier)
    - self.bare = bare-Repo als 'origin'
    - self.other = zweiter Klon, simuliert 'jemand anderes hat gepusht'
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-retry-"))
        self.bare = Path(tempfile.mkdtemp(prefix="ccb-retry-bare-"))
        _setup_git_repo(self.tmp)
        # bare-Repo als lokaler 'origin'
        _git("clone", "--bare", str(self.tmp), str(self.bare), cwd=self.tmp)
        _git("remote", "add", "origin", str(self.bare), cwd=self.tmp)
        _git("push", "--set-upstream", "origin", "main", cwd=self.tmp)
        # Store-Struktur im Haupt-Klon anlegen und initial pushen
        for sub in ("tasks/BRIDGE-0902", "audit"):
            (self.tmp / sub).mkdir(parents=True, exist_ok=True)
        (self.tmp / "tasks/BRIDGE-0902/task.yaml").write_text("k: v\n", encoding="utf-8")
        (self.tmp / "audit/audit.jsonl").write_text("", encoding="utf-8")
        _git("add", "tasks/BRIDGE-0902/task.yaml", "audit/audit.jsonl", cwd=self.tmp)
        _git("commit", "-m", "initial store files", cwd=self.tmp)
        _git("push", cwd=self.tmp)
        # Zweiter Klon NACH dem initialen Push (hat alle Store-Dateien)
        self.other = Path(tempfile.mkdtemp(prefix="ccb-retry-other-"))
        _git("clone", str(self.bare), str(self.other), cwd=self.tmp)
        _git("config", "user.email", "test@example.com", cwd=self.other)
        _git("config", "user.name", "Test", cwd=self.other)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.bare, ignore_errors=True)
        shutil.rmtree(self.other, ignore_errors=True)

    def _head_sha(self, repo=None):
        return _git("rev-parse", "HEAD", cwd=repo or self.tmp)

    def _bare_head_sha(self):
        return _git("rev-parse", "main", cwd=self.bare)

    def _commit_count_bare(self):
        return int(_git("rev-list", "--count", "main", cwd=self.bare))

    def _other_push(self, filename="README.md", content="other change\n"):
        """Anderer Klon schreibt eine nicht-konfliktierende Datei und pusht."""
        (self.other / filename).write_text(content, encoding="utf-8")
        _git("add", filename, cwd=self.other)
        _git("commit", "-m", "other commit", cwd=self.other)
        _git("push", cwd=self.other)

    # --- Erfolgsfall: Retry erfolgreich, beide Commits im Remote-Verlauf ------

    def test_retry_success_on_non_fast_forward(self):
        """Divergiertes Repo: Retry erkennt NFF, rebased, pushed erfolgreich."""
        # Zaehle vor dem fremden Push — beide Commits muessen danach im Remote sein
        before_bare_count = self._commit_count_bare()

        # Anderen Commit vor unserem push() einschieben -> NFF-Situation
        self._other_push("README.md", "other change\n")

        # Unsere Aenderung in task.yaml und audit
        (self.tmp / "tasks/BRIDGE-0902/task.yaml").write_text("changed\n", encoding="utf-8")
        (self.tmp / "audit/audit.jsonl").write_text("log\n", encoding="utf-8")

        result = gitops.git_commit(self.tmp, "task_copied", "BRIDGE-0902",
                                   "test-actor", push=True)

        self.assertTrue(result["committed"], result.get("error"))
        self.assertTrue(result["pushed"], result.get("error"))
        self.assertIsNone(result["error"])
        self.assertTrue(result["retried"])

        # Beide Commits (fremder + eigener) im bare-Repo vorhanden
        self.assertEqual(self._commit_count_bare(), before_bare_count + 2)

    # --- Rebase-Konflikt: fail-closed, sauberer Zustand danach ---------------

    def test_retry_rebase_conflict_fail_closed(self):
        """Inhaltlich widersprüchliche Aenderung -> fail-closed, kein Force-Push,
        kein haengender Rebase-Zustand."""
        # Anderer Klon aendert task.yaml (dieselbe Datei, die wir auch aendern)
        (self.other / "tasks/BRIDGE-0902/task.yaml").write_text("conflict A\n", encoding="utf-8")
        _git("add", "tasks/BRIDGE-0902/task.yaml", cwd=self.other)
        _git("commit", "-m", "conflict commit from other", cwd=self.other)
        _git("push", cwd=self.other)

        # Unsere Aenderung an derselben Datei (-> Rebase-Konflikt)
        (self.tmp / "tasks/BRIDGE-0902/task.yaml").write_text("conflict B\n", encoding="utf-8")
        (self.tmp / "audit/audit.jsonl").write_text("log\n", encoding="utf-8")

        result = gitops.git_commit(self.tmp, "task_copied", "BRIDGE-0902",
                                   "test-actor", push=True)

        self.assertTrue(result["committed"])   # lokal committet
        self.assertFalse(result["pushed"])     # nicht gepusht
        self.assertIsNotNone(result["error"])
        self.assertTrue(result["retried"])

        # Repo darf sich nicht in einem haengenden Rebase-Zustand befinden
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.tmp, capture_output=True, text=True, timeout=10,
        )
        # Kein 'rebase in progress' — git status gibt bei haengendem Rebase
        # eigentlich eine Meldung auf stderr; einfachste Pruefung: kein
        # .git/rebase-merge oder .git/rebase-apply Verzeichnis
        self.assertFalse((self.tmp / ".git" / "rebase-merge").exists(),
                         "Haengender Rebase-Zustand nach Konflikt (rebase-merge da)")
        self.assertFalse((self.tmp / ".git" / "rebase-apply").exists(),
                         "Haengender Rebase-Zustand nach Konflikt (rebase-apply da)")

    # --- Anderer Fehlertyp: kein Retry ausgeloest ----------------------------

    def test_non_nff_push_failure_no_retry(self):
        """Nicht erreichbarer Remote -> kein Retry, retried=False."""
        (self.tmp / "tasks/BRIDGE-0902/task.yaml").write_text("changed\n", encoding="utf-8")
        (self.tmp / "audit/audit.jsonl").write_text("log\n", encoding="utf-8")
        _git("remote", "set-url", "origin", "/nonexistent/nowhere", cwd=self.tmp)

        result = gitops.git_commit(self.tmp, "task_copied", "BRIDGE-0902",
                                   "test-actor", push=True)

        self.assertTrue(result["committed"])
        self.assertFalse(result["pushed"])
        self.assertIsNotNone(result["error"])
        self.assertFalse(result["retried"])

    # --- Zweiter Push-Versuch scheitert ebenfalls: kein dritter Versuch -------

    def test_retry_second_push_also_fails(self):
        """Zweiter Push (nach erfolgreichem Rebase) schlaegt ebenfalls fehl ->
        kein dritter Versuch, retried=True, pushed=False.

        Der erste Push schlaegt mit NFF fehl (echter divergierter Zustand).
        Nach fetch+rebase (echt) wird der zweite Push per Mock abgelehnt,
        um eine erneute Zwischenkollision zu simulieren, die zwischen Rebase
        und zweitem Push aus einem Unittest heraus nicht injizierbar ist.
        """
        from unittest.mock import patch, MagicMock

        # Anderen Commit einschieben -> NFF beim ersten Push (echt)
        self._other_push("README.md", "other change 2\n")

        (self.tmp / "tasks/BRIDGE-0902/task.yaml").write_text("changed2\n", encoding="utf-8")
        (self.tmp / "audit/audit.jsonl").write_text("log2\n", encoding="utf-8")

        real_run = subprocess.run
        push_calls = [0]

        def intercept(args, **kwargs):
            """Leitet alle Aufrufe an subprocess.run weiter, ausser den Pushes."""
            if isinstance(args, (list, tuple)) and len(args) >= 2 \
                    and args[0] == "git" and args[1] == "push":
                push_calls[0] += 1
                if push_calls[0] == 1:
                    # Erster Push: NFF simulieren (wie echter Fehler)
                    m = MagicMock()
                    m.returncode = 1
                    m.stderr = ("To origin\n"
                                "! [rejected] main -> main (non-fast-forward)\n"
                                "error: failed to push some refs")
                    m.stdout = ""
                    return m
                else:
                    # Zweiter Push (nach Rebase): auch Fehler -> kein dritter
                    m = MagicMock()
                    m.returncode = 1
                    m.stderr = "error: failed to push some refs (second attempt)"
                    m.stdout = ""
                    return m
            return real_run(args, **kwargs)

        with patch("subprocess.run", side_effect=intercept):
            result = gitops.git_commit(self.tmp, "task_copied", "BRIDGE-0902",
                                       "test-actor", push=True)

        self.assertTrue(result["committed"])
        self.assertFalse(result["pushed"])
        self.assertIsNotNone(result["error"])
        self.assertTrue(result["retried"])
        # Genau 2 Push-Versuche, kein dritter
        self.assertEqual(push_calls[0], 2)


if __name__ == "__main__":
    unittest.main()
