"""Hermetische Tests fuer die Maschinen-Registry (BRIDGE-016). stdlib unittest."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from bridge import registry  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"


def valid_registry(**over):
    doc = {
        "schema_version": "1.0",
        "kind": "bridge_machine_registry",
        "machines": {"HAM11": "E:\\_DEV", "DES11": "D:\\work"},
    }
    doc.update(over)
    return doc


def valid_profile(**over):
    doc = {
        "schema_version": "1.0",
        "kind": "bridge_project_profile",
        "project_id": "demo",
        "description": "Demo-Profil.",
        "repository": "Demo-Repo",
        "default_branch": "main",
        "task_prefix": "DEMO",
        "read_only": True,
    }
    doc.update(over)
    return doc


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccb-registry-"))
        (self.tmp / "projects").mkdir()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("CCB_PROJECT_BASE", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_registry(self, doc):
        (self.tmp / "registry.yaml").write_text(
            yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    def write_profile(self, dirname, doc):
        d = self.tmp / "projects" / dirname
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    # -- load_registry --------------------------------------------------

    def test_load_registry_ok(self):
        self.write_registry(valid_registry())
        doc = registry.load_registry(self.tmp, SCHEMA_DIR)
        self.assertEqual(doc["machines"]["HAM11"], "E:\\_DEV")

    def test_load_registry_missing_fails_closed(self):
        with self.assertRaises(registry.RegistryError):
            registry.load_registry(self.tmp, SCHEMA_DIR)

    def test_load_registry_invalid_fails_closed(self):
        bad = valid_registry()
        del bad["machines"]
        self.write_registry(bad)
        with self.assertRaises(registry.RegistryError):
            registry.load_registry(self.tmp, SCHEMA_DIR)

    # -- machine_name -------------------------------------------------

    def test_machine_name_explicit_wins(self):
        self.assertEqual(registry.machine_name("HAM11"), "HAM11")

    # -- resolve_base ----------------------------------------------

    def test_resolve_base_env_override(self):
        os.environ["CCB_PROJECT_BASE"] = "X:\\anywhere"
        # kein registry.yaml noetig, wenn der Override greift
        self.assertEqual(
            registry.resolve_base(self.tmp, SCHEMA_DIR, explicit_machine="NOPE11"),
            "X:\\anywhere")

    def test_resolve_base_known_machine(self):
        self.write_registry(valid_registry())
        self.assertEqual(
            registry.resolve_base(self.tmp, SCHEMA_DIR, explicit_machine="DES11"),
            "D:\\work")

    def test_resolve_base_unknown_machine_fails_closed(self):
        self.write_registry(valid_registry())
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.resolve_base(self.tmp, SCHEMA_DIR, explicit_machine="NOPE11")
        self.assertIn("NOPE11", str(ctx.exception))
        self.assertIn("CCB_PROJECT_BASE", str(ctx.exception))

    # -- project_local_path (fail-soft) --------------------------

    def test_project_local_path_ok(self):
        base = self.tmp / "base"
        (base / "Demo-Repo").mkdir(parents=True)
        self.write_registry(valid_registry(machines={"HERE": str(base)}))
        self.write_profile("demo", valid_profile())
        path = registry.project_local_path(
            self.tmp, SCHEMA_DIR, "demo", explicit_machine="HERE")
        self.assertEqual(path, str(base / "Demo-Repo"))

    def test_project_local_path_missing_profile_returns_none(self):
        self.write_registry(valid_registry(machines={"HERE": str(self.tmp)}))
        self.assertIsNone(registry.project_local_path(
            self.tmp, SCHEMA_DIR, "nope", explicit_machine="HERE"))

    def test_project_local_path_unknown_machine_returns_none(self):
        self.write_registry(valid_registry())
        self.write_profile("demo", valid_profile())
        self.assertIsNone(registry.project_local_path(
            self.tmp, SCHEMA_DIR, "demo", explicit_machine="NOPE11"))

    def test_project_local_path_missing_dir_returns_none(self):
        self.write_registry(valid_registry(machines={"HERE": str(self.tmp / "base")}))
        self.write_profile("demo", valid_profile())
        # Basis existiert, aber <base>/Demo-Repo nicht
        (self.tmp / "base").mkdir()
        self.assertIsNone(registry.project_local_path(
            self.tmp, SCHEMA_DIR, "demo", explicit_machine="HERE"))

    def test_repo_registry_is_valid(self):
        doc = registry.load_registry(REPO_ROOT)
        self.assertEqual(doc["kind"], "bridge_machine_registry")
        self.assertIn("HAM11", doc["machines"])


if __name__ == "__main__":
    unittest.main()
