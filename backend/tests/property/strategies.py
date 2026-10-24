"""Shared Hypothesis strategies for routing property tests."""

from __future__ import annotations

from hypothesis import strategies as st

from app.domain.models import AudioEvent, RouteDecision, Service

_EVENT_KINDS = [
    "scream",
    "glass_breaking",
    "siren",
    "smoke_alarm",
    "explosion",
    "alarm_generic",
]

_KEYWORDS = [
    "help",
    "fire",
    "smoke",
    "burning",
    "bleeding",
    "hurt",
    "unconscious",
    "break-in",
    "attacker",
    "gun",
    "crash",
    "no",
    "not",
    "nothing to see here",
]

_SERVICES: list[Service] = ["police", "fire", "medical"]


def confidences() -> st.SearchStrategy[float]:
    return st.floats(min_value=0.0, max_value=1.0)


def audio_events() -> st.SearchStrategy[list[AudioEvent]]:
    event = st.builds(
        AudioEvent,
        kind=st.sampled_from(_EVENT_KINDS),
        confidence=confidences(),
    )
    return st.lists(event, max_size=5)


def transcripts() -> st.SearchStrategy[str]:
    """Keyword soup (to hit the rules) mixed with arbitrary text (to find surprises)."""
    keyword_soup = st.lists(st.sampled_from(_KEYWORDS), max_size=6).map(" ".join)
    return st.one_of(
        keyword_soup,
        st.text(max_size=60),
        st.tuples(keyword_soup, st.text(max_size=20)).map(" ".join),
    )


def route_decisions() -> st.SearchStrategy[RouteDecision]:
    service_map = st.dictionaries(
        keys=st.sampled_from(_SERVICES),
        values=confidences(),
        max_size=3,
    )
    return st.builds(
        RouteDecision,
        services=service_map,
        status=st.sampled_from(["provisional", "refined"]),
        pinned=st.lists(st.sampled_from(_SERVICES), max_size=3, unique=True),
    )
