"""Hermetische Tests für die Projektprofile (BRIDGE-010). stdlib unittest."""

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

from bridge import profiles  # noqa: E402
from bridge.cli import main  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"


def valid_profile(**over):
    doc = {
        "schema_version": "1.0",
        "kind": "bridge_project_profile",
        "project_id": "demo",
        "description": "Demo-Profil.",
        "repository": "Demo",
        "default_branch": "main",
        "task_prefix": "DEMO",
        "read_only": True,
    }
    doc.update(over)
    return doc


class ProfilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-profiles-"))
        (self.tmp / "projects").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_profile(self, dirname, doc):
        d = self.tmp / "projects" / dirname
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.yaml").write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # -- load_profile ------------------------------------------------

    def test_load_valid_profile(self):
        self.write_profile("demo", valid_profile(project_id="demo"))
        doc = profiles.load_profile(self.tmp, "demo", schema_dir=SCHEMA_DIR)
        self.assertEqual(doc["project_id"], "demo")
        self.assertEqual(doc["task_prefix"], "DEMO")
        self.assertIs(doc["read_only"], True)

    def test_missing_profile_fails_closed(self):
        with self.assertRaises(profiles.ProfileError):
            profiles.load_profile(self.tmp, "nope", schema_dir=SCHEMA_DIR)

    def test_read_only_is_required(self):
        bad = valid_profile(project_id="demo")
        del bad["read_only"]
        self.write_profile("demo", bad)
        with self.assertRaises(profiles.ProfileError):
            profiles.load_profile(self.tmp, "demo", schema_dir=SCHEMA_DIR)

    def test_unknown_field_rejected(self):
        self.write_profile("demo", valid_profile(project_id="demo", extra_feld="x"))
        with self.assertRaises(profiles.ProfileError):
            profiles.load_profile(self.tmp, "demo", schema_dir=SCHEMA_DIR)

    def test_project_id_must_match_directory(self):
        self.write_profile("demo", valid_profile(project_id="anders"))
        with self.assertRaises(profiles.ProfileError):
            profiles.load_profile(self.tmp, "demo", schema_dir=SCHEMA_DIR)

    # -- list_profiles / validate_profile --------------------------

    def test_list_profiles_ignores_examples(self):
        self.write_profile("alpha", valid_profile(project_id="alpha"))
        self.write_profile("beta", valid_profile(project_id="beta"))
        ex = self.tmp / "projects" / "examples"
        ex.mkdir()
        (ex / "project.yaml").write_text("kind: bridge_project_profile\n", encoding="utf-8")
        self.assertEqual(profiles.list_profiles(self.tmp), ["alpha", "beta"])

    def test_validate_profile_pure(self):
        p = self.tmp / "x.yaml"
        p.write_text(yaml.safe_dump(valid_profile()), encoding="utf-8")
        self.assertEqual(
            profiles.validate_profile(p, SCHEMA_DIR)["kind"], "bridge_project_profile")
        bad = valid_profile()
        del bad["task_prefix"]
        p.write_text(yaml.safe_dump(bad), encoding="utf-8")
        with self.assertRaises(profiles.ProfileError):
            profiles.validate_profile(p, SCHEMA_DIR)

    # -- reales Repo-Profil -------------------------------------

    def test_repo_profile_is_valid(self):
        doc = profiles.load_profile(REPO_ROOT, "codex-control-bridge")
        self.assertEqual(doc["task_prefix"], "BRIDGE")
        self.assertIs(doc["read_only"], False)
        self.assertIn("codex-control-bridge", profiles.list_profiles(REPO_ROOT))


class CliProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-cli-proj-"))
        (self.tmp / "projects").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_profile(self, dirname, doc):
        d = self.tmp / "projects" / dirname
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.tmp),
                         "--schema-dir", str(SCHEMA_DIR), *args])
        return code, out.getvalue(), err.getvalue()

    def test_project_list_and_show(self):
        self.write_profile("demo", valid_profile(project_id="demo"))
        code, out, _ = self.cli("project", "list")
        self.assertEqual(code, 0)
        self.assertIn("demo", out)
        self.assertIn("task_prefix=DEMO", out)
        code, out, _ = self.cli("project", "show", "demo")
        self.assertEqual(code, 0)
        self.assertIn("task_prefix: DEMO", out)

    def test_project_show_unknown_exit1(self):
        code, _, err = self.cli("project", "show", "nope")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def test_project_validate_invalid_exit1(self):
        bad = valid_profile()
        del bad["read_only"]
        p = self.tmp / "bad.yaml"
        p.write_text(yaml.safe_dump(bad), encoding="utf-8")
        code, _, err = self.cli("project", "validate", str(p))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
