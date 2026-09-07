"""Maschinen-Registry - COMPUTERNAME -> lokale Basis (BRIDGE-016).

Zweck ist eng: die Registry (`registry.yaml` in der Repo-Wurzel) wird
**ausschliesslich** von der Befehlsreferenz (`bridge commands`) gebraucht, um
reale, kopierfertige lokale Pfade anderer Projekt-Repos aufzuloesen
(`<basis>\\<repository>`). Auftraege selbst liegen alle in EINEM zentralen Store
(diesem Repo) - die Registry findet keine Auftraege.

Fail-closed beim Laden/Validieren und in ``resolve_base`` (eine unbekannte
Maschine ohne ``CCB_PROJECT_BASE`` liefert lieber eine klare Fehlermeldung als
einen geratenen Pfad). ``project_local_path`` ist bewusst fail-SOFT: es gibt bei
jedem Fehler ``None`` zurueck und wirft nie, damit das Board nie wegen einem
einzelnen nicht aufloesbaren Projekt abbricht.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from bridge import profiles
from bridge.store import StoreError, _FORMAT_CHECKER

_SCHEMA_NAME = "registry.schema.yaml"
_REGISTRY_NAME = "registry.yaml"


class RegistryError(StoreError):
    """Die Maschinen-Registry fehlt, verletzt ihr Schema oder kennt die
    aktuelle Maschine nicht (fail-closed)."""


def _schema_dir(root, schema_dir) -> Path:
    if schema_dir is not None:
        return Path(schema_dir)
    return Path(root).resolve() / "schemas"


def _validator(root, schema_dir) -> Draft202012Validator:
    path = _schema_dir(root, schema_dir) / _SCHEMA_NAME
    try:
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RegistryError(f"Registry-Schema nicht lesbar: {path} ({exc})") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise RegistryError(f"Registry-Schema fehlerhaft: {path} ({exc})") from exc
    return Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)


def load_registry(root, schema_dir=None) -> dict:
    """Laedt ``registry.yaml`` (Repo-Wurzel) und validiert gegen
    ``registry.schema.yaml`` - fail-closed, gleiches Muster wie
    ``profiles.load_profile``."""
    path = Path(root).resolve() / _REGISTRY_NAME
    if not path.is_file():
        raise RegistryError(f"Maschinen-Registry nicht gefunden: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(f"Maschinen-Registry nicht lesbar: {path} ({exc})") from exc
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RegistryError(f"Maschinen-Registry kein gueltiges YAML: {path} ({exc})") from exc
    if not isinstance(doc, dict):
        raise RegistryError(f"Maschinen-Registry ist kein Objekt: {path}")
    validator = _validator(root, schema_dir)
    errors = sorted(validator.iter_errors(doc), key=lambda e: str(list(e.path)))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "(Wurzel)"
        raise RegistryError(f"Maschinen-Registry ungueltig: {first.message} [Feld: {where}]")
    return doc


def machine_name(explicit=None) -> str:
    """Aktueller Maschinenname. ``explicit`` (z. B. ein ``--machine``-Flag) hat
    Vorrang, sonst ``COMPUTERNAME`` aus der Umgebung, sonst ``platform.node()``
    als Fallback (Nicht-Windows / Tests)."""
    if explicit:
        return explicit
    env = os.environ.get("COMPUTERNAME")
    if env:
        return env
    return platform.node()


def resolve_base(root, schema_dir=None, *, explicit_machine=None,
                 env_override_name="CCB_PROJECT_BASE") -> str:
    """Lokale Basis, unter der die Projekt-Repos liegen.

    1. Ist ``env_override_name`` in der Umgebung gesetzt -> dessen Wert.
    2. Sonst: Registry laden, ``machine_name(explicit_machine)`` nachschlagen.
    3. Unbekannte Maschine -> ``RegistryError`` (fail-closed).
    """
    override = os.environ.get(env_override_name)
    if override:
        return override
    registry = load_registry(root, schema_dir)
    name = machine_name(explicit_machine)
    machines = registry.get("machines", {})
    if name not in machines:
        known = ", ".join(sorted(machines)) or "(keine)"
        raise RegistryError(
            f"Maschine {name!r} ist nicht in registry.yaml eingetragen "
            f"(bekannt: {known}). Entweder die Maschine dort ergaenzen oder "
            f"{env_override_name} auf die lokale Basis setzen.")
    return machines[name]


def project_local_path(root, schema_dir=None, project_id=None, *,
                       explicit_machine=None) -> str | None:
    """Aufgeloester lokaler Pfad des Projekt-Repos (``<basis>/<repository>``)
    oder ``None``.

    Fail-SOFT (anders als ``resolve_base``): wenn die Basis nicht aufloesbar
    ist, das Profil fehlt/kaputt ist ODER der Pfad auf DIESER Maschine nicht
    existiert -> ``None``. Wirft nie. Der Aufrufer entscheidet, wie das
    angezeigt wird.
    """
    try:
        base = resolve_base(root, schema_dir, explicit_machine=explicit_machine)
    except (RegistryError, StoreError, OSError):
        return None
    try:
        profile = profiles.load_profile(root, project_id, schema_dir=schema_dir)
    except (profiles.ProfileError, StoreError, OSError):
        return None
    repository = profile.get("repository")
    if not repository:
        return None
    path = os.path.join(base, repository)
    if not os.path.isdir(path):
        return None
    return path
