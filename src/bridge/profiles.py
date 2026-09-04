"""Projektprofile / Adapter - Schema + Loader (BRIDGE-010).

Projektspezifische Regeln leben im Profil (``projects/<id>/project.yaml``), NICHT
im projektunabhängigen Core. BRIDGE-010 stellt nur Schema-Validierung und eine
Laderoutine bereit; die Verdrahtung in Store/Runner (task_prefix erzwingen,
read_only/allowed_machines prüfen) folgt bewusst später (BRIDGE-011).

Reine stdlib zzgl. pyyaml/jsonschema (bereits Projektabhängigkeit über die
Ablage-Schicht). Fail-closed: fehlende Datei, Schemafehler oder ein ``project_id``,
das nicht zum Verzeichnisnamen passt, führen zu ``ProfileError``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# src-Layout: direkter Skriptaufruf braucht das Paketverzeichnis auf dem Pfad.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from bridge.store import StoreError, _FORMAT_CHECKER

_SCHEMA_NAME = "project.schema.yaml"
_EXAMPLES_DIR = "examples"


class ProfileError(StoreError):
    """Ein Projektprofil fehlt, verletzt sein Schema oder ist inkonsistent (fail-closed)."""


def _projects_dir(root) -> Path:
    return Path(root).resolve() / "projects"


def _validator(schema_dir) -> Draft202012Validator:
    path = Path(schema_dir) / _SCHEMA_NAME
    try:
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"Profil-Schema nicht lesbar: {path} ({exc})") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ProfileError(f"Profil-Schema fehlerhaft: {path} ({exc})") from exc
    return Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)


def _load_yaml(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"Profil nicht lesbar: {path} ({exc})") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileError(f"Profil kein gültiges YAML: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"Profil ist kein Objekt: {path}")
    return data


def profile_path(root, project_id: str) -> Path:
    """``<root>/projects/<id>/project.yaml`` (ohne Seiteneffekt)."""
    return _projects_dir(root) / project_id / "project.yaml"


def validate_profile(path_or_doc, schema_dir) -> dict:
    """Reine Schema-Validierung ohne ID-/Verzeichnisprüfung. Gibt das dict zurück."""
    if isinstance(path_or_doc, (str, Path)):
        doc = _load_yaml(Path(path_or_doc))
    elif isinstance(path_or_doc, dict):
        doc = path_or_doc
    else:
        raise ProfileError("validate_profile erwartet einen Pfad oder ein dict.")
    validator = _validator(schema_dir)
    errors = sorted(validator.iter_errors(doc), key=lambda e: str(list(e.path)))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "(Wurzel)"
        raise ProfileError(f"Profil ungültig: {first.message} [Feld: {where}]")
    return doc


def load_profile(root, project_id: str, schema_dir=None) -> dict:
    """Lädt ``projects/<id>/project.yaml``, validiert gegen das Schema und prüft
    die Konsistenz von ``project_id`` mit dem Verzeichnisnamen (fail-closed)."""
    path = profile_path(root, project_id)
    if not path.is_file():
        raise ProfileError(f"Projektprofil nicht gefunden: {path}")
    sd = Path(schema_dir) if schema_dir is not None else Path(root).resolve() / "schemas"
    doc = validate_profile(path, sd)
    if doc.get("project_id") != project_id:
        raise ProfileError(
            f"project_id im Profil ({doc.get('project_id')!r}) passt nicht zum "
            f"Verzeichnisnamen ({project_id!r}).")
    return doc


def list_profiles(root) -> list[str]:
    """Alle realen Profile (``projects/<id>/project.yaml``), sortiert.
    ``projects/examples/`` wird NICHT als echtes Profil gezählt."""
    base = _projects_dir(root)
    if not base.is_dir():
        return []
    out = []
    for entry in base.iterdir():
        if not entry.is_dir() or entry.name == _EXAMPLES_DIR:
            continue
        if (entry / "project.yaml").is_file():
            out.append(entry.name)
    return sorted(out)
