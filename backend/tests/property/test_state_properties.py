"""Property-based tests for the state machine (P7) and sequential routing (P8)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.analyzers.rule_router import RuleRouter
from app.domain.models import AudioEvent, CaptureState
from app.domain.models import RouteDecision as RD
from app.domain.state import ORDER, IllegalTransition, rank, transition
from tests.property.strategies import audio_events, transcripts


@given(requests=st.lists(st.sampled_from(ORDER), max_size=30))
def test_p7_only_single_forward_steps_are_applied(requests: list[CaptureState]) -> None:
    """P7: a transition succeeds iff it moves exactly one step forward; nothing else."""
    current: CaptureState = "idle"
    applied = 0
    for target in requests:
        if rank(target) == rank(current) + 1:
            current = transition(current, target)
            applied += 1
        else:
            with pytest.raises(IllegalTransition):
                transition(current, target)
    # Every applied step advanced the state by exactly one, so rank == steps applied.
    assert rank(current) == applied


router = RuleRouter(min_service_conf=0.3, high_conf=0.7, guarantee_min_event_conf=0.5)


@given(
    first_conf=st.floats(min_value=0.5, max_value=1.0),
    later=st.lists(st.tuples(transcripts(), audio_events()), max_size=8),
)
def test_p8_confident_smoke_alarm_keeps_fire_for_the_rest_of_the_capture(
    first_conf: float, later: list[tuple[str, list[AudioEvent]]]
) -> None:
    """P8: once a confident smoke_alarm is heard, every later decision still has fire."""
    smoke = [AudioEvent(kind="smoke_alarm", confidence=first_conf)]
    decision: RD = router.route("help", smoke, None, "provisional")
    assert "fire" in decision.services
    for text, events in later:
        decision = router.route(text, events, decision, "provisional")
        assert "fire" in decision.services
