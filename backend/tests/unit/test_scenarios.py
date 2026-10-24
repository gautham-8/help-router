"""Unit tests for scenario fixtures and their routing (Requirement 6.3)."""

from __future__ import annotations

import asyncio

from app.analyzers.interfaces import AudioChunk
from app.analyzers.mock.detector import MockAudioEventDetector
from app.analyzers.mock.scenarios import list_scenarios
from app.analyzers.mock.transcriber import MockTranscriber
from app.analyzers.rule_router import RuleRouter

REQUIRED = {"kitchen-fire", "break-in", "car-crash-injuries", "multi-service"}


def test_required_scenarios_present() -> None:
    ids = {s["id"] for s in list_scenarios()}
    assert REQUIRED.issubset(ids)


def _route_full_scenario(scenario_id: str) -> set[str]:
    transcriber = MockTranscriber()
    detector = MockAudioEventDetector()
    router = RuleRouter(min_service_conf=0.3, high_conf=0.7)

    async def run() -> set[str]:
        prior = None
        for i in range(6):
            chunk = AudioChunk(report_id="t", chunk_index=i, scenario=scenario_id)
            t = (await transcriber.transcribe(chunk)).text
            events = await detector.detect(chunk)
            status = "refined" if i == 5 else "provisional"
            prior = router.route(t, events, prior, status)
        assert prior is not None
        return set(prior.services)

    return asyncio.run(run())


def test_kitchen_fire_routes_fire() -> None:
    assert "fire" in _route_full_scenario("kitchen-fire")


def test_break_in_routes_police() -> None:
    assert "police" in _route_full_scenario("break-in")


def test_car_crash_routes_police_and_medical() -> None:
    services = _route_full_scenario("car-crash-injuries")
    assert {"police", "medical"}.issubset(services)


def test_multi_service_routes_all_three() -> None:
    assert _route_full_scenario("multi-service") == {"police", "fire", "medical"}
