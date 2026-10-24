"""Property-based tests for the rule router (design properties P1-P6, P8, plus P9)."""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from app.analyzers.rule_router import RuleRouter
from app.domain.models import ALL_SERVICES, AudioEvent
from app.domain.models import RouteDecision as RD
from tests.property.strategies import audio_events, confidences, route_decisions, transcripts

HIGH_CONF = 0.7
MIN_CONF = 0.3
GUARANTEE_CONF = 0.5

router = RuleRouter(
    min_service_conf=MIN_CONF, high_conf=HIGH_CONF, guarantee_min_event_conf=GUARANTEE_CONF
)


@given(text=transcripts(), events=audio_events(), prior=st.none() | route_decisions())
def test_p1_confidence_bounds(text: str, events: list[AudioEvent], prior: RD | None) -> None:
    """P1: every routed confidence is within [0, 1]."""
    decision = router.route(text, events, prior, "provisional")
    for conf in decision.services.values():
        assert 0.0 <= conf <= 1.0


@given(text=transcripts(), events=audio_events(), prior=st.none() | route_decisions())
def test_p2_confident_smoke_alarm_implies_fire(
    text: str, events: list[AudioEvent], prior: RD | None
) -> None:
    """P2: a smoke_alarm at or above the guarantee confidence always yields fire."""
    confident_smoke = any(
        e.kind == "smoke_alarm" and e.confidence >= GUARANTEE_CONF for e in events
    )
    decision = router.route(text, events, prior, "provisional")
    if confident_smoke:
        assert "fire" in decision.services
        assert "fire" in decision.pinned


@given(text=transcripts(), events=audio_events(), prior=st.none() | route_decisions())
def test_p3_determinism(text: str, events: list[AudioEvent], prior: RD | None) -> None:
    """P3: same (text, events, prior) -> same decision."""
    assert router.route(text, events, prior, "provisional") == router.route(
        text, events, prior, "provisional"
    )


@given(text=transcripts(), events=audio_events(), prior=st.none() | route_decisions())
def test_p4_every_routed_service_is_justified(
    text: str, events: list[AudioEvent], prior: RD | None
) -> None:
    """P4: a routed service is at/above the threshold, pinned, or committed in the prior."""
    decision = router.route(text, events, prior, "provisional")
    assert set(decision.services) <= set(ALL_SERVICES)
    for service, conf in decision.services.items():
        committed = prior is not None and prior.services.get(service, -1.0) >= HIGH_CONF
        assert conf >= MIN_CONF or service in decision.pinned or committed


@given(
    text=transcripts(),
    events=audio_events(),
    prior=route_decisions(),
    min_conf=confidences(),
    high_conf=confidences(),
)
def test_p5_committed_service_is_never_dropped(
    text: str, events: list[AudioEvent], prior: RD, min_conf: float, high_conf: float
) -> None:
    """P5: a service at/above high_conf in the prior is still routed afterwards.

    Thresholds are generated, including min_conf > high_conf, so the "keep a committed
    service even when it fell below the threshold" branch is actually exercised.
    """
    r = RuleRouter(min_service_conf=min_conf, high_conf=high_conf)
    committed = {s for s, c in prior.services.items() if c >= high_conf}
    decision = r.route(text, events, prior, "refined")
    assert committed <= set(decision.services)


@given(text=transcripts(), events=audio_events(), prior=st.none() | route_decisions())
def test_p6_needs_attention_iff_nothing_routed(
    text: str, events: list[AudioEvent], prior: RD | None
) -> None:
    """P6: needs_attention is true exactly when no service was routed."""
    decision = router.route(text, events, prior, "provisional")
    assert decision.needs_attention == (len(decision.services) == 0)


@given(
    prefix=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
    suffix=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
)
def test_p9_keywords_match_whole_words_only(prefix: str, suffix: str) -> None:
    """P9: a keyword buried inside a longer word ("begun") never routes anything."""
    for keyword in ("gun", "fire", "hurt", "smoke", "crash"):
        decision = router.route(f"{prefix}{keyword}{suffix}", [], None, "provisional")
        assert decision.services == {}


@given(
    faint=st.lists(
        st.floats(min_value=0.0, max_value=GUARANTEE_CONF, exclude_max=True), max_size=5
    ),
    text=transcripts(),
)
def test_p11_faint_smoke_alarms_never_pin_fire(faint: list[float], text: str) -> None:
    """P11: smoke alarms below the guarantee confidence never pin fire on their own."""
    events = [AudioEvent(kind="smoke_alarm", confidence=c) for c in faint]
    decision = router.route(text, events, None, "provisional")
    assert decision.pinned == []


@given(text=transcripts(), prior=route_decisions())
def test_p10_confidence_fades_without_fresh_evidence(text: str, prior: RD) -> None:
    """P10: with no events and no keyword hits, confidence decays by CARRY_DECAY."""
    if router.route(text, [], None, "provisional").services:
        return  # the text itself carries evidence; this property is about silence
    decision = router.route(text, [], prior, "provisional")
    for service, conf in decision.services.items():
        if service in decision.pinned:
            continue  # pinned services are floored at MIN_SERVICE_CONF
        assert conf <= prior.services.get(service, 0.0) * router.carry_decay + 1e-12
