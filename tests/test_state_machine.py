"""Tests für den Übergangs-Validator (BRIDGE-004). stdlib unittest, kein pytest."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bridge import state_machine as sm  # noqa: E402,F401
from bridge.state_machine import (  # noqa: E402
    STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    ModelError,
    TransitionError,
    assert_transition,
    is_allowed,
    load_model,
)


class TransitionRules(unittest.TestCase):
    def test_allowed_transition(self):
        self.assertTrue(is_allowed("CREATED", "READY"))

    def test_disallowed_transition(self):
        self.assertFalse(is_allowed("CREATED", "RUNNING"))

    def test_unknown_from_state_fail_closed(self):
        self.assertFalse(is_allowed("NOPE", "READY"))
        with self.assertRaises(TransitionError):
            assert_transition("NOPE", "READY")

    def test_unknown_to_state_fail_closed(self):
        self.assertFalse(is_allowed("CREATED", "NOPE"))
        with self.assertRaises(TransitionError):
            assert_transition("CREATED", "NOPE")

    def test_archived_is_terminal(self):
        self.assertIn("ARCHIVED", TERMINAL_STATES)
        self.assertEqual(TRANSITIONS["ARCHIVED"], [])
        self.assertFalse(is_allowed("ARCHIVED", "READY"))

    def test_assert_transition_raises_on_disallowed(self):
        with self.assertRaises(TransitionError):
            assert_transition("CREATED", "RUNNING")


class ModelIntegrity(unittest.TestCase):
    def test_every_state_has_transitions_entry(self):
        for state in STATES:
            self.assertIn(state, TRANSITIONS, f"{state} fehlt in TRANSITIONS")

    def test_every_target_is_known_state(self):
        for from_state, targets in TRANSITIONS.items():
            for target in targets:
                self.assertIn(target, STATES, f"{from_state} -> {target}: unbekanntes Ziel")

    def test_missing_model_file_fails_closed(self):
        with self.assertRaises(ModelError):
            load_model("schemas/does-not-exist.yaml")


if __name__ == "__main__":
    unittest.main()
