"""Forward-only capture/route state machine.

Lifecycle: ``idle -> listening -> provisional -> refined -> closed``.

The machine never moves backward or skips a step. Illegal transition requests are
rejected (raise :class:`IllegalTransition`), never silently applied. This is a
property-based-testing target (design property P7).
"""

from __future__ import annotations

from .models import CaptureState

# Canonical ordering; index is the "rank" of a state.
ORDER: tuple[CaptureState, ...] = (
    "idle",
    "listening",
    "provisional",
    "refined",
    "closed",
)

_RANK: dict[CaptureState, int] = {state: i for i, state in enumerate(ORDER)}

# Allowed single-step transitions. Only forward by exactly one step.
_ALLOWED: dict[CaptureState, set[CaptureState]] = {
    "idle": {"listening"},
    "listening": {"provisional"},
    "provisional": {"refined"},
    "refined": {"closed"},
    "closed": set(),
}


class IllegalTransition(ValueError):
    """Raised when a requested state transition is not permitted."""

    def __init__(self, current: CaptureState, target: CaptureState) -> None:
        super().__init__(f"illegal transition: {current} -> {target}")
        self.current = current
        self.target = target


def rank(state: CaptureState) -> int:
    """Return the ordinal position of a state in the lifecycle."""
    return _RANK[state]


def can_transition(current: CaptureState, target: CaptureState) -> bool:
    """Whether moving from ``current`` to ``target`` is permitted."""
    return target in _ALLOWED[current]


def transition(current: CaptureState, target: CaptureState) -> CaptureState:
    """Return ``target`` if the move is legal, else raise :class:`IllegalTransition`."""
    if not can_transition(current, target):
        raise IllegalTransition(current, target)
    return target
