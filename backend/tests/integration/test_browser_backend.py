"""The default `browser` backend: the device sends transcript + sound events.

These tests play the part of the caller's browser. The scripted-scenario path is covered
in test_capture_flow.py; here no scenario is named, so the signals come from the client.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.config import get_settings
from app.main import app

client = TestClient(app)


def create(**extra: Any) -> str:
    resp = client.post("/reports", json={"lat": 42.36, "lon": -71.06, **extra})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


def chunk(ws: WebSocketTestSession, index: int, **signals: Any) -> dict[str, Any]:
    ws.send_json({"type": "chunk", "chunk_index": index, **signals})
    return ws.receive_json()  # type: ignore[no-any-return]


def stream(report_id: str) -> Any:
    return client.websocket_connect(f"/ws/reports/{report_id}/stream")


def queue_ids(service: str) -> list[str]:
    return [e["report_id"] for e in client.get(f"/queues/{service}").json()]


def test_default_backend_is_browser_and_needs_no_scenario() -> None:
    assert client.get("/health").json()["analyzer_backend"] == "browser"


def test_spoken_words_alone_route_the_report() -> None:
    rid = create()
    with stream(rid) as ws:
        msg = chunk(ws, 0, transcript="help someone is breaking in", events=[])
    assert msg["type"] == "route"
    assert set(msg["decision"]["services"]) == {"police"}
    assert rid in queue_ids("police")
    assert queue_ids("fire") == []


def test_sounds_alone_route_the_report() -> None:
    rid = create()
    with stream(rid) as ws:
        msg = chunk(ws, 0, transcript="", events=[{"kind": "smoke_alarm", "confidence": 0.9}])
    assert set(msg["decision"]["services"]) == {"fire"}
    assert msg["decision"]["pinned"] == ["fire"]


def test_words_and_sounds_combine_across_chunks_into_several_services() -> None:
    rid = create()
    with stream(rid) as ws:
        first = chunk(ws, 0, transcript="there is smoke everywhere", events=[])
        assert set(first["decision"]["services"]) == {"fire"}
        second = chunk(
            ws,
            1,
            transcript="my friend is bleeding and unconscious",
            events=[{"kind": "scream", "confidence": 0.8}],
        )
    assert {"fire", "medical"} <= set(second["decision"]["services"])
    assert rid in queue_ids("fire")
    assert rid in queue_ids("medical")


def test_silence_is_flagged_for_a_responder_not_guessed() -> None:
    rid = create()
    with stream(rid) as ws:
        msg = chunk(ws, 0, transcript="", events=[])
    assert msg["decision"]["services"] == {}
    assert msg["decision"]["needs_attention"] is True


def test_unavailable_signals_are_recorded_not_fatal() -> None:
    # `null` = the device could not produce the signal (e.g. no speech recognition).
    rid = create()
    with stream(rid) as ws:
        msg = chunk(ws, 0, transcript=None, events=[{"kind": "glass_breaking", "confidence": 0.95}])
        assert msg["type"] == "route"
        assert "police" in msg["decision"]["services"]
        nothing = chunk(ws, 1)  # neither signal at all
        assert nothing["type"] == "route"
        assert "police" in nothing["decision"]["services"]  # earlier evidence persists


def test_a_full_browser_capture_ends_refined_and_closed() -> None:
    rid = create()
    with stream(rid) as ws:
        for i in range(6):
            msg = chunk(ws, i, transcript="the kitchen is on fire", events=[])
            assert msg["type"] == "route"
        assert msg["state"] == "refined"
        ws.send_json({"type": "end"})
        assert ws.receive_json()["state"] == "closed"


@pytest.mark.parametrize(
    "signals",
    [
        {"transcript": 5},
        {"transcript": "x" * 2001},
        {"transcript": ["a"]},
        {"events": "smoke_alarm"},
        {"events": [{"kind": "volcano", "confidence": 0.5}]},
        {"events": [{"kind": "siren", "confidence": 1.5}]},
        {"events": [{"kind": "siren", "confidence": -0.1}]},
        {"events": [{"kind": "siren"}]},
        {"events": [{"kind": "siren", "confidence": 0.5}] * 21},
    ],
)
def test_malformed_signals_are_rejected_and_the_stream_survives(signals: dict[str, Any]) -> None:
    rid = create()
    with stream(rid) as ws:
        err = chunk(ws, 0, **signals)
        assert err["type"] == "error"
        assert "invalid transcript or events" in err["detail"]
        # The bad chunk was not counted, so index 0 is still the next one.
        assert chunk(ws, 0, transcript="fire", events=[])["type"] == "route"


def test_a_demo_scenario_overrides_the_device_signals() -> None:
    # Scripted demos stay deterministic even if a client also sends signals.
    rid = create(scenario="kitchen-fire")
    with stream(rid) as ws:
        msg = chunk(ws, 0, transcript="there is a gun", events=[])
    assert set(msg["decision"]["services"]) == {"fire"}


def test_live_backend_without_keys_fails_at_report_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANALYZER_BACKEND", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    resp = client.post("/reports", json={})
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]
    # ...but a scripted demo still works, because scenarios never need keys.
    assert client.post("/reports", json={"scenario": "kitchen-fire"}).status_code == 200


# --- triage: unclassifiable reports must reach a human -----------------------


def test_a_silent_report_lands_in_triage_where_a_human_can_see_it() -> None:
    rid = create()
    with stream(rid) as ws:
        for i in range(6):
            msg = chunk(ws, i, transcript="", events=[])
        assert msg["decision"]["services"] == {}
    assert queue_ids("triage") == [rid]
    assert all(queue_ids(s) == [] for s in ("police", "fire", "medical"))


def test_triage_assign_puts_it_in_a_service_queue_and_clears_triage() -> None:
    rid = create()
    with stream(rid) as ws:
        chunk(ws, 0, transcript="", events=[])
    assert queue_ids("triage") == [rid]

    resp = client.post(
        f"/reports/{rid}/triage/assign", params={"service": "medical", "responder": "d1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"report_id": rid, "assigned_to": "medical"}
    assert queue_ids("triage") == []
    assert queue_ids("medical") == [rid]


def test_triage_assign_validates_its_input() -> None:
    rid = create()
    with stream(rid) as ws:
        chunk(ws, 0, transcript="", events=[])
    assert client.post(f"/reports/{rid}/triage/assign").status_code == 422
    assert (
        client.post(f"/reports/{rid}/triage/assign", params={"service": "coastguard"}).status_code
        == 422
    )
    assert (
        client.post(f"/reports/{rid}/triage/assign", params={"service": "triage"}).status_code
        == 422
    )
    assert client.post("/reports/nope/triage/assign", params={"service": "fire"}).status_code == 404


def test_triage_can_be_dismissed_but_not_confirmed() -> None:
    rid = create()
    with stream(rid) as ws:
        chunk(ws, 0, transcript="", events=[])
    assert client.post(f"/reports/{rid}/triage/confirm").status_code == 409
    assert (
        client.post(f"/reports/{rid}/triage/reject", params={"responder": "d1"}).status_code == 200
    )
    assert queue_ids("triage") == []


def test_triage_respects_the_dashboard_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_TOKEN", "s3cret")
    get_settings.cache_clear()
    rid = create()
    with stream(rid) as ws:
        chunk(ws, 0, transcript="", events=[])
    assert (
        client.post(f"/reports/{rid}/triage/assign", params={"service": "fire"}).status_code == 401
    )
    ok = client.post(
        f"/reports/{rid}/triage/assign",
        params={"service": "fire"},
        headers={"X-Dashboard-Token": "s3cret"},
    )
    assert ok.status_code == 200


def test_a_report_the_system_classifies_later_leaves_triage_by_itself() -> None:
    rid = create()
    with stream(rid) as ws:
        chunk(ws, 0, transcript="", events=[])
        assert queue_ids("triage") == [rid]
        chunk(ws, 1, transcript="the house is on fire", events=[])
    assert queue_ids("triage") == []
    assert queue_ids("fire") == [rid]
