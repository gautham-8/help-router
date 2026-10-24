"""Unit tests for the forward-only state machine."""

from __future__ import annotations

import pytest

from app.domain.state import IllegalTransition, can_transition, transition


def test_legal_forward_path() -> None:
    state = "idle"
    for target in ("listening", "provisional", "refined", "closed"):
        state = transition(state, target)  # type: ignore[arg-type]
    assert state == "closed"


def test_backward_transition_rejected() -> None:
    with pytest.raises(IllegalTransition):
        transition("provisional", "listening")


def test_skip_transition_rejected() -> None:
    with pytest.raises(IllegalTransition):
        transition("idle", "provisional")


def test_closed_is_terminal() -> None:
    assert can_transition("closed", "refined") is False
    with pytest.raises(IllegalTransition):
        transition("closed", "idle")
