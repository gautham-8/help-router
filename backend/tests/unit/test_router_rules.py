"""Unit tests for the rule router's rule table, decay, negation, and thresholds."""

from __future__ import annotations

import pytest

from app.analyzers.rule_router import RuleRouter
from app.domain.models import AudioEvent, RouteDecision

router = RuleRouter(min_service_conf=0.3, high_conf=0.7, carry_decay=0.85)


# --- expanded vocabulary: real phrasings callers actually use ----------------


@pytest.mark.parametrize(
    "text,service",
    [
        ("I'm being killed and slaughtered", "police"),
        ("someone is trying to kill me", "police"),
        ("there's an intruder in my house", "police"),
        ("someone broke into my house", "police"),
        ("he has a knife", "police"),
        ("active shooter", "police"),
        ("I'm drowning", "medical"),
        ("I'm falling from the sky", "medical"),
        ("the water is over my head", "medical"),
        ("he's not breathing", "medical"),
        ("she had a seizure", "medical"),
        ("my dad collapsed", "medical"),
        ("I think it's a heart attack", "medical"),
        ("the house is on fire", "fire"),
        ("I smell gas", "fire"),
        ("the stove caught fire", "fire"),
        ("there was an explosion", "fire"),
    ],
)
def test_real_phrasings_route(text: str, service: str) -> None:
    assert service in router.route(text, [], None, "provisional").services


def test_vocabulary_is_large() -> None:
    # The whole point of this pass: a broad vocabulary, not five keywords.
    from app.analyzers.rule_router import (
        _CRASH_TERMS,
        _FIRE_TERMS,
        _MEDICAL_TERMS,
        _POLICE_TERMS,
    )

    total = len(set(_FIRE_TERMS + _MEDICAL_TERMS + _POLICE_TERMS + _CRASH_TERMS))
    assert total >= 300


def test_smoke_alarm_routes_fire() -> None:
    events = [AudioEvent(kind="smoke_alarm", confidence=0.95)]
    decision = router.route("help there's smoke", events, None, "provisional")
    assert "fire" in decision.services
    assert not decision.needs_attention


def test_break_in_keywords_route_police() -> None:
    decision = router.route("someone is breaking in", [], None, "provisional")
    assert "police" in decision.services


def test_injury_keywords_route_medical() -> None:
    decision = router.route("a person is bleeding and unconscious", [], None, "provisional")
    assert "medical" in decision.services


def test_blood_alone_routes_medical() -> None:
    decision = router.route("Blood blood blood", [], None, "provisional")
    assert "medical" in decision.services
    assert not decision.needs_attention


def test_bullet_wound_routes_medical_and_police() -> None:
    text = "I see a person with a bullet in his chest I see a person with a bullet"
    decision = router.route(text, [], None, "provisional")
    assert {"medical", "police"} <= set(decision.services)


def test_multi_service_fans_out() -> None:
    events = [
        AudioEvent(kind="explosion", confidence=0.9),
        AudioEvent(kind="scream", confidence=0.7),
    ]
    decision = router.route("fire and someone with a gun, people are hurt", events, None, "refined")
    assert set(decision.services) == {"police", "fire", "medical"}


def test_nothing_indicated_sets_needs_attention() -> None:
    decision = router.route("hello hello hello", [], None, "provisional")
    assert decision.services == {}
    assert decision.needs_attention is True


def test_confidence_clamped_to_one() -> None:
    events = [AudioEvent(kind="smoke_alarm", confidence=1.0)]
    prior = RouteDecision(services={"fire": 0.9}, status="provisional")
    decision = router.route("fire burning flames", events, prior, "refined")
    assert decision.services["fire"] == 1.0


# --- whole-word matching and negation ----------------------------------------


@pytest.mark.parametrize("text", ["it has begun", "the gunk is everywhere", "a firefly", "hurtle"])
def test_keywords_inside_longer_words_do_not_match(text: str) -> None:
    assert router.route(text, [], None, "provisional").services == {}


@pytest.mark.parametrize(
    "text",
    [
        "there is no fire here",
        "there is not a fire",
        "nobody is hurt but no smoke",
        "he doesn't have a gun",
        "it isn't burning",
    ],
)
def test_negated_keywords_do_not_route(text: str) -> None:
    assert router.route(text, [], None, "provisional").services == {}


@pytest.mark.parametrize(
    "text",
    [
        "no sorry I mean there is a fire",  # "no" is too far from "fire"
        "no, help, there's a fire",  # comma ends the clause
        "no I'm okay but there is a fire",  # "but" ends the clause
        "there is no gas and a fire",  # "and" ends the clause
        "I am not sure what to do. Fire!",  # sentence break
    ],
)
def test_negation_does_not_cancel_real_emergencies(text: str) -> None:
    # A missed emergency costs more than a false alarm, so negation stays narrow.
    assert "fire" in router.route(text, [], None, "provisional").services


def test_not_breathing_is_a_medical_keyword_not_a_negated_one() -> None:
    assert "medical" in router.route("he is not breathing", [], None, "provisional").services


def test_curly_apostrophe_negation() -> None:
    assert router.route("he doesn\u2019t have a gun", [], None, "provisional").services == {}


# --- smoke alarm guarantee ---------------------------------------------------


def test_faint_smoke_alarm_does_not_force_fire() -> None:
    events = [AudioEvent(kind="smoke_alarm", confidence=0.1)]
    decision = router.route("hello", events, None, "provisional")
    assert "fire" not in decision.services
    assert decision.pinned == []


def test_smoke_alarm_pins_fire_for_later_chunks() -> None:
    first = router.route("help", [AudioEvent(kind="smoke_alarm", confidence=0.9)], None)
    assert first.pinned == ["fire"]
    later = first
    for _ in range(12):  # long silence: confidence fades but fire stays routed
        later = router.route("", [], later)
    assert "fire" in later.services
    assert later.services["fire"] >= router.min_service_conf


# --- carry-forward, decay, and notes -----------------------------------------


def test_confidence_decays_without_fresh_evidence() -> None:
    prior = RouteDecision(services={"medical": 0.8}, status="provisional")
    decision = router.route("quiet", [], prior, "provisional")
    assert decision.services["medical"] == pytest.approx(0.8 * 0.85)


def test_faded_service_is_dropped_with_a_note() -> None:
    prior = RouteDecision(services={"medical": 0.34}, status="provisional")
    decision = router.route("quiet", [], prior, "provisional")  # 0.34 * 0.85 = 0.289 < 0.3
    assert "medical" not in decision.services
    assert any("medical dropped" in n for n in decision.notes)


def test_committed_service_stays_visible_with_downgrade_note() -> None:
    # With a strict threshold, a committed service that decays below it is kept and
    # flagged instead of vanishing (Requirement 4.4).
    strict = RuleRouter(min_service_conf=0.9, high_conf=0.7)
    prior = RouteDecision(services={"fire": 0.8}, status="provisional")
    decision = strict.route("quiet", [], prior, "refined")
    assert "fire" in decision.services
    assert any("fire downgraded" in n for n in decision.notes)


def test_notes_are_not_duplicated_across_steps() -> None:
    strict = RuleRouter(min_service_conf=0.9, high_conf=0.7, carry_decay=1.0)
    prior = RouteDecision(services={"fire": 0.8}, status="provisional")
    once = strict.route("quiet", [], prior)
    twice = strict.route("quiet", [], once)
    assert len(twice.notes) == len(set(twice.notes))


def test_repeated_evidence_reinforces() -> None:
    first = router.route("there is a fire", [], None)
    second = router.route("the fire is bigger", [], first)
    assert second.services["fire"] > first.services["fire"]


# --- construction ------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_service_conf": -0.1},
        {"high_conf": 1.1},
        {"carry_decay": 0.0},
        {"carry_decay": 1.5},
        {"guarantee_min_event_conf": 2.0},
    ],
)
def test_invalid_thresholds_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        RuleRouter(**kwargs)
