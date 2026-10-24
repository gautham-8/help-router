"""End-to-end flow over the mock backend: create -> stream -> route -> confirm.

Uses FastAPI's TestClient (no network, no keys). Requirements 5, 6.1, 6.4.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.main import app

client = TestClient(app)


def stream_url(report_id: str) -> str:
    return f"/ws/reports/{report_id}/stream"


def create(scenario: str | None = "kitchen-fire", **extra: Any) -> str:
    resp = client.post(
        "/reports", json={"scenario": scenario, "lat": 42.36, "lon": -71.06, **extra}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "No real emergency service" in body["demo_safety"]
    return str(body["id"])


def send_chunk(ws: WebSocketTestSession, index: int, **extra: Any) -> dict[str, Any]:
    ws.send_json({"type": "chunk", "chunk_index": index, **extra})
    return ws.receive_json()  # type: ignore[no-any-return]


def queue_ids(service: str) -> list[str]:
    return [e["report_id"] for e in client.get(f"/queues/{service}").json()]


def eventually(check: Callable[[], bool], timeout: float = 2.0) -> bool:
    """The server finishes disconnect cleanup on its own task; poll briefly."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return check()


# --- health and creation -----------------------------------------------------


def test_health_reports_demo_safety() -> None:
    data = client.get("/health").json()
    assert data["analyzer_backend"] == "browser"
    assert data["real_dispatch_enabled"] is False
    assert data["auth_required"] is False


def test_unknown_scenario_is_rejected_up_front() -> None:
    resp = client.post("/reports", json={"scenario": "does-not-exist"})
    assert resp.status_code == 400
    assert "does-not-exist" in resp.json()["detail"]


@pytest.mark.parametrize(
    "body", [{"lat": 91}, {"lon": -181}, {"accuracy_m": -1}, {"scenario": "x" * 65}]
)
def test_invalid_report_fields_are_rejected(body: dict[str, Any]) -> None:
    assert client.post("/reports", json=body).status_code == 422


def test_report_without_scenario_or_location_is_allowed() -> None:
    assert client.post("/reports", json={}).status_code == 200


def test_unknown_report_stream_is_refused() -> None:
    with client.websocket_connect(stream_url("nope")) as ws:
        assert ws.receive_json()["type"] == "error"


# --- the happy path ----------------------------------------------------------


def test_kitchen_fire_flow_provisional_then_refined_then_confirm() -> None:
    report_id = create("kitchen-fire")

    decisions = []
    with client.websocket_connect(stream_url(report_id)) as ws:
        for i in range(6):
            msg = send_chunk(ws, i)
            assert msg["type"] == "route"
            decisions.append(msg)
        ws.send_json({"type": "end"})
        closed = ws.receive_json()

    assert closed["type"] == "closed"
    assert closed["state"] == "closed"
    assert closed["decision"]["status"] == "refined"

    assert decisions[0]["decision"]["status"] == "provisional"
    assert decisions[0]["state"] == "provisional"
    assert decisions[-1]["decision"]["status"] == "refined"
    assert decisions[-1]["state"] == "refined"
    assert set(decisions[-1]["decision"]["services"]) == {"fire"}

    assert report_id in queue_ids("fire")
    assert queue_ids("police") == []
    assert queue_ids("medical") == []

    confirm = client.post(f"/reports/{report_id}/fire/confirm", params={"responder": "disp-1"})
    assert confirm.status_code == 200
    assert confirm.json()["confirmed"] is True
    assert confirm.json()["responder"] == "disp-1"


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("kitchen-fire", {"fire"}),
        ("break-in", {"police"}),
        ("car-crash-injuries", {"police", "medical"}),
        ("multi-service", {"police", "fire", "medical"}),
    ],
)
def test_each_scenario_lands_in_the_right_queues(scenario: str, expected: set[str]) -> None:
    report_id = create(scenario)
    with client.websocket_connect(stream_url(report_id)) as ws:
        for i in range(6):
            send_chunk(ws, i)
        ws.send_json({"type": "end"})
        ws.receive_json()

    for service in ("police", "fire", "medical"):
        assert (report_id in queue_ids(service)) == (service in expected), service


def test_dashboard_gets_snapshot_then_live_updates() -> None:
    report_id = create("break-in")
    with client.websocket_connect("/ws/dashboard") as dash:
        initial = [dash.receive_json() for _ in range(4)]
        assert {m["service"] for m in initial} == {"police", "fire", "medical", "triage"}
        assert all(m["queue"] == [] for m in initial)

        with client.websocket_connect(stream_url(report_id)) as ws:
            send_chunk(ws, 0)
        update = dash.receive_json()
        assert update["type"] == "queue_update"
        assert update["service"] == "police"
        assert update["queue"][0]["report_id"] == report_id


# --- ending a capture --------------------------------------------------------


def test_early_end_finalizes_the_report() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        send_chunk(ws, 0)
        send_chunk(ws, 1)
        ws.send_json({"type": "end"})
        closed = ws.receive_json()

    assert closed["state"] == "closed"
    assert closed["decision"]["status"] == "refined"
    assert any("ended early" in n for n in closed["decision"]["notes"])
    entry = client.get("/queues/fire").json()[0]
    assert entry["route_status"] == "refined"


def test_dropped_connection_finalizes_the_report() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        send_chunk(ws, 0)
    # No "end" was sent: the queue entry must not stay provisional forever.
    assert eventually(
        lambda: any(e["route_status"] == "refined" for e in client.get("/queues/fire").json())
    )


# --- hostile / sloppy input on the capture stream ----------------------------


def test_out_of_order_chunk_is_rejected_then_stream_recovers() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        err = send_chunk(ws, 3)
        assert err["type"] == "error"
        assert "expected chunk 0" in err["detail"]
        assert send_chunk(ws, 0)["type"] == "route"


def test_duplicate_chunk_does_not_double_count() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        assert send_chunk(ws, 0)["type"] == "route"
        assert send_chunk(ws, 0)["type"] == "error"
    entry = client.get("/queues/fire").json()[0]
    assert entry["transcript"] == "help there's smoke in the kitchen"
    assert len(entry["events"]) == 1


def test_chunk_after_the_final_one_is_rejected_and_state_stays_refined() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        for i in range(6):
            send_chunk(ws, i)
        err = send_chunk(ws, 6)
        assert err["type"] == "error"
    assert client.get("/queues/fire").json()[0]["route_status"] == "refined"


@pytest.mark.parametrize("bad_index", ["0", 1.5, None, True, [0]])
def test_non_integer_chunk_index_is_rejected(bad_index: Any) -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        err = send_chunk(ws, bad_index)
        assert err["type"] == "error"
        assert send_chunk(ws, 0)["type"] == "route"  # connection survived


def test_malformed_messages_do_not_kill_the_stream() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        ws.send_text("this is not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_text("[1, 2, 3]")
        assert ws.receive_json()["type"] == "error"
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "bogus"})
        assert ws.receive_json()["type"] == "error"
        assert send_chunk(ws, 0)["type"] == "route"


def test_audio_payload_is_validated() -> None:
    report_id = create("kitchen-fire")
    with client.websocket_connect(stream_url(report_id)) as ws:
        assert send_chunk(ws, 0, audio_b64="%%%not base64%%%")["type"] == "error"
        assert send_chunk(ws, 0, audio_b64=123)["type"] == "error"
        assert send_chunk(ws, 0, audio_b64="A" * 4_000_000)["type"] == "error"
        assert send_chunk(ws, 0, audio_b64="aGVsbG8=")["type"] == "route"


# --- human decisions ---------------------------------------------------------


def test_rejected_report_does_not_reappear_on_the_next_chunk() -> None:
    report_id = create("break-in")
    with client.websocket_connect(stream_url(report_id)) as ws:
        send_chunk(ws, 0)
        assert report_id in queue_ids("police")

        resp = client.post(f"/reports/{report_id}/police/reject", params={"responder": "d2"})
        assert resp.status_code == 200
        assert report_id not in queue_ids("police")

        send_chunk(ws, 1)
        send_chunk(ws, 2)
    assert report_id not in queue_ids("police")


def test_confirm_after_reject_is_404_and_reject_after_confirm_is_409() -> None:
    report_id = create("multi-service")
    with client.websocket_connect(stream_url(report_id)) as ws:
        for i in range(6):
            send_chunk(ws, i)

    assert client.post(f"/reports/{report_id}/police/reject").status_code == 200
    assert client.post(f"/reports/{report_id}/police/confirm").status_code == 404

    assert client.post(f"/reports/{report_id}/fire/confirm").status_code == 200
    assert client.post(f"/reports/{report_id}/fire/reject").status_code == 409


def test_unknown_service_and_report_are_404() -> None:
    assert client.get("/queues/coastguard").status_code == 404
    assert client.post("/reports/nope/fire/confirm").status_code == 404


# --- access control ----------------------------------------------------------


@pytest.fixture
def token_required(monkeypatch: pytest.MonkeyPatch) -> str:
    from app.config import get_settings

    monkeypatch.setenv("DASHBOARD_TOKEN", "s3cret")
    get_settings.cache_clear()
    return "s3cret"


def test_dashboard_endpoints_require_the_token_when_set(token_required: str) -> None:
    assert client.get("/health").json()["auth_required"] is True

    report_id = create("kitchen-fire")  # callers never need the token
    with client.websocket_connect(stream_url(report_id)) as ws:
        send_chunk(ws, 0)

    assert client.get("/queues/fire").status_code == 401
    assert client.get("/queues/fire", headers={"X-Dashboard-Token": "wrong"}).status_code == 401
    ok = client.get("/queues/fire", headers={"X-Dashboard-Token": token_required})
    assert ok.status_code == 200
    assert [e["report_id"] for e in ok.json()] == [report_id]

    assert client.post(f"/reports/{report_id}/fire/confirm").status_code == 401
    assert client.post(f"/reports/{report_id}/fire/reject").status_code == 401
    confirmed = client.post(
        f"/reports/{report_id}/fire/confirm", headers={"X-Dashboard-Token": token_required}
    )
    assert confirmed.status_code == 200


def test_dashboard_websocket_requires_the_token_when_set(token_required: str) -> None:
    from starlette.websockets import WebSocketDisconnect

    for url in ("/ws/dashboard", "/ws/dashboard?token=wrong"):
        with client.websocket_connect(url) as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
        assert closed.value.code == 1008
    with client.websocket_connect(f"/ws/dashboard?token={token_required}") as dash:
        assert dash.receive_json()["type"] == "queue_update"
