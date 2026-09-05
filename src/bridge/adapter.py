"""Read-only-Projektadapter (BRIDGE-011): Git-Stand eines fremden Projekts lesen,
ohne je zu schreiben.

Nur Mechanismus - KEINE Verbindung zum echten Dorfschaft-Repo, keine WSL-
Zugriffe. Der Adapter setzt ausschließlich Kommandos ab, deren Subkommando in
`schemas/git-readonly-allowlist.yaml` (SSOT) steht; jedes andere Subkommando
wird VOR jeder Ausführung abgelehnt (fail-closed). `read_only: true` aus dem
Projektprofil (BRIDGE-010) wird hart erzwungen.

Reine stdlib (`subprocess` für Git, `yaml` nur zum Einlesen der Allowlist -
bereits Projektabhängigkeit). Keine CLI-Verdrahtung in diesem Paket.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST_NAME = "git-readonly-allowlist.yaml"


class ReadOnlyViolation(Exception):
    """Ein Kommando/Profil verletzt die Read-only-Grenze (fail-closed)."""


class AdapterError(Exception):
    """Ein erlaubtes Git-Kommando ist fehlgeschlagen (z. B. Repo nicht gefunden)."""


def _default_schema_dir() -> Path:
    return _REPO_ROOT / "schemas"


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def load_allowlist(schema_dir=None) -> set[str]:
    """Liest die erlaubten Lese-Subkommandos aus der YAML (SSOT, keine Hartkodierung)."""
    path = Path(schema_dir) if schema_dir is not None else _default_schema_dir()
    path = path / _ALLOWLIST_NAME
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdapterError(f"Allowlist nicht lesbar: {path} ({exc})") from exc
    except yaml.YAMLError as exc:
        raise AdapterError(f"Allowlist kein gültiges YAML: {path} ({exc})") from exc
    if not isinstance(data, dict) or data.get("kind") != "bridge_git_readonly_allowlist":
        raise AdapterError(f"Allowlist unbrauchbar (kind falsch): {path}")
    cmds = data.get("allowed_git_subcommands")
    if not isinstance(cmds, list) or not cmds:
        raise AdapterError(f"Allowlist: 'allowed_git_subcommands' fehlt/leer: {path}")
    return set(cmds)


def run_readonly_git(repo_path, args, *, allowlist) -> str:
    """Setzt EIN Git-Kommando gegen ``repo_path`` ab, NUR wenn ``args[0]`` in
    ``allowlist`` steht. Die Prüfung läuft VOR jeder Ausführung (fail-closed);
    bei Ablehnung wird nichts gestartet, das fremde Repo bleibt unverändert."""
    if not args:
        raise ReadOnlyViolation("Kein git-Subkommando angegeben.")
    subcommand = args[0]
    if subcommand not in allowlist:
        raise ReadOnlyViolation(
            f"git-Subkommando nicht in der Read-only-Allowlist: {subcommand!r}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdapterError(f"git {' '.join(args)} nicht ausführbar: {exc}") from exc
    if proc.returncode != 0:
        raise AdapterError(
            f"git {' '.join(args)} fehlgeschlagen (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


class ReadOnlyProjectAdapter:
    """Liest den Git-Stand eines fremden, read-only-Projekts (z. B. Dorfschaft).

    Schreibt NIE ins fremde Repo. Jedes Kommando läuft über
    :func:`run_readonly_git` gegen die aus der YAML geladene Allowlist.
    """

    def __init__(self, profile, repo_path, schema_dir=None):
        if profile.get("read_only") is not True:
            raise ReadOnlyViolation(
                "Adapter nur für read_only-Projekte (Profil hat read_only != true).")
        self.profile = profile
        self.repo_path = Path(repo_path)
        self.allowlist = load_allowlist(schema_dir)

    def _git(self, *args: str) -> str:
        return run_readonly_git(self.repo_path, list(args), allowlist=self.allowlist)

    def git_info(self, base_head=None) -> dict:
        """Dieselben Felder wie ``importer.collect_git_info`` - ausschließlich
        über Allowlist-Kommandos ermittelt (Branch via ``rev-parse --abbrev-ref``)."""
        toplevel = self._git("rev-parse", "--show-toplevel")
        info = {
            "repository": Path(toplevel).name,
            "branch": self._git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": self._git("rev-parse", "HEAD"),
            "base_head": base_head,
            "commits": [],
            "changed_files": [],
        }
        if base_head:
            shas = _lines(self._git("rev-list", "--reverse", f"{base_head}..HEAD"))
            info["commits"] = [
                {"sha": sha, "message": self._git("log", "-1", "--format=%s", sha)}
                for sha in shas
            ]
            info["changed_files"] = _lines(
                self._git("diff", "--name-only", base_head, "HEAD"))
        else:
            info["changed_files"] = _lines(
                self._git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"))
        return info

    def as_git_info_fn(self):
        """Callable ``(root=None, base_head=None)`` - ``root`` wird ignoriert,
        genutzt wird ``self.repo_path``. Direkt als ``git_info_fn`` für
        ``importer.import_result`` verwendbar: das Ergebnis landet im
        CCB-Store, die Git-Provenienz kommt aus dem fremden (Dorfschaft-)Repo."""
        def _git_info_fn(root=None, base_head=None):
            return self.git_info(base_head=base_head)
        return _git_info_fn
