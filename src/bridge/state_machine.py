"""Übergangs-Validator für das Bridge-Zustandsmodell (BRIDGE-004).

Die erlaubten Zustandsübergänge stammen ausschließlich aus
``schemas/state-model.yaml`` (SSOT). Dieses Modul kodiert KEINE Übergangstabelle.

Fail-closed: Ein Übergang gilt nur als erlaubt, wenn er im Modell ausdrücklich
gelistet ist. Unbekannte Zustände oder eine fehlende/fehlerhafte Modelldatei
führen zu einem Fehler, nie zu einer stillschweigenden Erlaubnis.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

DEFAULT_MODEL_PATH = "schemas/state-model.yaml"
_REPO_ROOT = Path(__file__).resolve().parents[2]


class ModelError(Exception):
    """Das Zustandsmodell fehlt oder ist unbrauchbar."""


class TransitionError(Exception):
    """Ein Zustandsübergang ist nicht erlaubt oder nicht bewertbar."""


def load_model(path: str = DEFAULT_MODEL_PATH) -> dict:
    """Lädt das Zustandsmodell aus einer YAML-Datei und prüft es fail-closed."""
    model_path = Path(path)
    if not model_path.is_absolute():
        model_path = _REPO_ROOT / model_path

    try:
        raw = model_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelError(f"Modelldatei nicht lesbar: {model_path} ({exc})") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ModelError(f"Modelldatei ist kein gültiges YAML: {model_path} ({exc})") from exc

    if not isinstance(data, dict):
        raise ModelError(f"Modell hat kein Objekt an der Wurzel: {model_path}")

    states = data.get("states")
    transitions = data.get("transitions")
    terminal = data.get("terminal_states", [])

    if not isinstance(states, list) or not states:
        raise ModelError("Modell: 'states' fehlt oder ist leer.")
    if not isinstance(transitions, dict) or not transitions:
        raise ModelError("Modell: 'transitions' fehlt oder ist leer.")
    if not isinstance(terminal, list):
        raise ModelError("Modell: 'terminal_states' muss eine Liste sein.")

    state_set = set(states)

    for state in states:
        if state not in transitions:
            raise ModelError(f"Modell: Zustand ohne Übergangs-Eintrag: {state}")
    for from_state, targets in transitions.items():
        if from_state not in state_set:
            raise ModelError(f"Modell: unbekannter Ausgangszustand in 'transitions': {from_state}")
        if not isinstance(targets, list):
            raise ModelError(f"Modell: Ziele von {from_state} sind keine Liste.")
        for target in targets:
            if target not in state_set:
                raise ModelError(f"Modell: unbekanntes Ziel '{target}' bei '{from_state}'.")
    for state in terminal:
        if state not in state_set:
            raise ModelError(f"Modell: unbekannter terminaler Zustand: {state}")

    return data


def _derive(model: dict) -> tuple[list, list, dict]:
    states = list(model["states"])
    terminal = list(model.get("terminal_states", []))
    transitions = {key: list(value) for key, value in model["transitions"].items()}
    return states, terminal, transitions


_MODEL = load_model()
STATES, TERMINAL_STATES, TRANSITIONS = _derive(_MODEL)


def is_allowed(from_state: str, to_state: str) -> bool:
    """True nur, wenn beide Zustände bekannt sind und der Übergang gelistet ist."""
    if from_state not in STATES or to_state not in STATES:
        return False
    return to_state in TRANSITIONS.get(from_state, [])


def assert_transition(from_state: str, to_state: str) -> None:
    """Wirft TransitionError, wenn der Übergang nicht erlaubt ist (fail-closed)."""
    if from_state not in STATES:
        raise TransitionError(f"Unbekannter Ausgangszustand: {from_state!r}")
    if to_state not in STATES:
        raise TransitionError(f"Unbekannter Zielzustand: {to_state!r}")
    if to_state not in TRANSITIONS.get(from_state, []):
        allowed = ", ".join(TRANSITIONS.get(from_state, [])) or "(keine)"
        raise TransitionError(
            f"Übergang {from_state} -> {to_state} nicht erlaubt. Erlaubte Ziele: {allowed}"
        )


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Aufruf: python src/bridge/state_machine.py <FROM> <TO>", file=sys.stderr)
        return 2
    from_state, to_state = argv
    try:
        assert_transition(from_state, to_state)
    except TransitionError as exc:
        print(f"DENIED: {exc}")
        return 1
    print("ALLOWED")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
