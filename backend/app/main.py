"""Help Router FastAPI application.

Endpoints:
  POST /reports                           create a report (optionally naming a demo scenario)
  WS   /ws/reports/{id}/stream            caller streams chunks; server streams decisions
  GET  /scenarios                         list available demo scenarios
  GET  /queues/{service}                  current queue snapshot            (token if set)
  WS   /ws/dashboard                      responder live queue updates      (token if set)
  POST /reports/{id}/{service}/confirm    human-confirmed dispatch          (token if set)
  POST /reports/{id}/{service}/reject     human rejection                   (token if set)

WebSockets live under /ws so a dev proxy can forward them without also swallowing the
/dashboard web page.

DEMO SAFETY: no real emergency service is ever contacted (see dispatch.queues).

ACCESS CONTROL: with DASHBOARD_TOKEN unset the API is open, which is fine for a local
demo. Set it before exposing the app anywhere else; the responder name is a label the
client supplies, not an identity.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from app.analyzers.factory import get_analyzers
from app.analyzers.interfaces import AudioChunk
from app.analyzers.mock.scenarios import ScenarioError, get_scenario, list_scenarios
from app.config import get_settings
from app.dispatch.hub_ws import DashboardBroadcaster
from app.dispatch.queues import REAL_DISPATCH_ENABLED, DecisionConflict, DispatchHub
from app.domain.models import (
    ALL_QUEUES,
    ALL_SERVICES,
    AudioEvent,
    Location,
    QueueName,
    Report,
    Service,
)
from app.routing.orchestrator import CaptureOrchestrator, ChunkRejected

MAX_REPORTS = 500

app = FastAPI(title="Help Router", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Dashboard-Token"],
)

# In-memory state for the demo.
_reports: OrderedDict[str, Report] = OrderedDict()
_hub = DispatchHub()
_broadcaster = DashboardBroadcaster()


def reset_state() -> None:
    """Forget every report and queue (used by tests)."""
    _reports.clear()
    _hub.clear()


# --- helpers -----------------------------------------------------------------


def _valid_queue(name: str) -> QueueName:
    if name not in ALL_QUEUES:
        raise HTTPException(status_code=404, detail=f"unknown queue: {name}")
    return name  # type: ignore[return-value]


def _valid_service(name: str) -> Service:
    if name not in ALL_SERVICES:
        raise HTTPException(status_code=422, detail=f"not a service: {name}")
    return name  # type: ignore[return-value]


def _token_ok(provided: str | None) -> bool:
    expected = get_settings().dashboard_token
    if not expected:
        return True
    return secrets.compare_digest((provided or "").encode(), expected.encode())


def _require_token(provided: str | None) -> None:
    if not _token_ok(provided):
        raise HTTPException(status_code=401, detail="dashboard token required")


def _decode_audio(value: Any, max_bytes: int) -> bytes:
    """Decode an optional base64 audio payload, enforcing a size limit."""
    if value is None:
        return b""
    if not isinstance(value, str):
        raise ValueError("audio_b64 must be a string")
    if len(value) > (max_bytes * 4) // 3 + 8:
        raise ValueError("audio chunk is too large")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio_b64 is not valid base64") from exc
    if len(data) > max_bytes:
        raise ValueError("audio chunk is too large")
    return data


async def _broadcast_touched(touched: list[QueueName]) -> None:
    for service in touched:
        await _broadcaster.broadcast(
            {"type": "queue_update", "service": service, "queue": _hub.snapshot(service)}
        )


# --- models ------------------------------------------------------------------


class CreateReportBody(BaseModel):
    scenario: str | None = Field(default=None, max_length=64)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)


class CreateReportResponse(BaseModel):
    id: str
    demo_safety: str


class ChunkSignals(BaseModel):
    """What the caller's browser worked out about a chunk (``browser`` backend).

    ``None`` means the device could not produce that signal; ``""`` / ``[]`` means it
    produced it and heard nothing. Bounded so a client cannot bloat a report.
    """

    transcript: str | None = Field(default=None, max_length=2000)
    events: list[AudioEvent] | None = Field(default=None, max_length=20)


# --- REST --------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "analyzer_backend": settings.analyzer_backend,
        "real_dispatch_enabled": REAL_DISPATCH_ENABLED,
        "auth_required": bool(settings.dashboard_token),
    }


@app.get("/scenarios")
async def scenarios() -> list[dict[str, str]]:
    return list_scenarios()


@app.post("/reports", response_model=CreateReportResponse)
async def create_report(body: CreateReportBody) -> CreateReportResponse:
    # A demo scenario is valid whatever the backend: it selects the scripted analyzers.
    if body.scenario is not None:
        try:
            get_scenario(body.scenario)
        except ScenarioError as exc:
            raise HTTPException(
                status_code=400, detail=f"unknown scenario: {body.scenario}"
            ) from exc

    # Fail here, with a clear message, if the configured backend is unusable.
    try:
        get_analyzers(body.scenario)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    report_id = secrets.token_urlsafe(9)
    known = body.lat is not None and body.lon is not None
    location = Location(lat=body.lat, lon=body.lon, accuracy_m=body.accuracy_m, known=known)
    _reports[report_id] = Report(id=report_id, location=location, scenario=body.scenario)

    while len(_reports) > MAX_REPORTS:
        old_id, _ = _reports.popitem(last=False)
        _hub.forget(old_id)

    return CreateReportResponse(
        id=report_id,
        demo_safety="No real emergency service is contacted. Human confirmation required.",
    )


@app.get("/queues/{service}")
async def queue_snapshot(
    service: str, x_dashboard_token: str | None = Header(default=None)
) -> list[dict[str, Any]]:
    _require_token(x_dashboard_token)
    return _hub.snapshot(_valid_queue(service))


@app.post("/reports/{report_id}/{service}/confirm")
async def confirm(
    report_id: str,
    service: str,
    responder: str | None = Query(default=None, max_length=64),
    x_dashboard_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_dashboard_token)
    svc = _valid_queue(service)
    try:
        status = _hub.confirm(svc, report_id, responder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DecisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _broadcast_touched([svc])
    return status.model_dump(mode="json")


@app.post("/reports/{report_id}/triage/assign")
async def assign_from_triage(
    report_id: str,
    service: str = Query(...),
    responder: str | None = Query(default=None, max_length=64),
    x_dashboard_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Send an unclassified report to a service queue (a human decision)."""
    _require_token(x_dashboard_token)
    target = _valid_service(service)
    try:
        touched = _hub.assign(report_id, target, responder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _broadcast_touched(touched)
    return {"report_id": report_id, "assigned_to": target}


@app.post("/reports/{report_id}/{service}/reject")
async def reject(
    report_id: str,
    service: str,
    responder: str | None = Query(default=None, max_length=64),
    x_dashboard_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_dashboard_token)
    svc = _valid_queue(service)
    try:
        status = _hub.reject(svc, report_id, responder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DecisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _broadcast_touched([svc])
    return status.model_dump(mode="json")


# --- WebSockets --------------------------------------------------------------


@app.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket, token: str | None = Query(default=None)) -> None:
    if not _token_ok(token):
        # Accept first so the browser sees close code 1008 (policy violation) instead of
        # an opaque handshake failure, and knows not to keep retrying.
        await ws.accept()
        await ws.close(code=1008)
        return
    await _broadcaster.connect(ws)
    try:
        for service in ALL_QUEUES:
            await ws.send_json(
                {"type": "queue_update", "service": service, "queue": _hub.snapshot(service)}
            )
        while True:
            await ws.receive_text()  # keepalive; the dashboard sends no commands here
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await _broadcaster.disconnect(ws)


async def _finalize_and_publish(orchestrator: CaptureOrchestrator, report: Report) -> None:
    if orchestrator.finalize(report):
        await _broadcast_touched(_hub.apply_route(report))


@app.websocket("/ws/reports/{report_id}/stream")
async def capture_stream(ws: WebSocket, report_id: str) -> None:
    await ws.accept()
    report = _reports.get(report_id)
    if report is None:
        await ws.send_json({"type": "error", "detail": "unknown report"})
        await ws.close()
        return

    settings = get_settings()
    orchestrator = CaptureOrchestrator(get_analyzers(report.scenario), settings.num_chunks)

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except (ValueError, KeyError):
                await ws.send_json({"type": "error", "detail": "messages must be JSON text"})
                continue
            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "detail": "message must be a JSON object"})
                continue

            kind = msg.get("type")

            if kind == "chunk":
                index = msg.get("chunk_index")
                if not isinstance(index, int) or isinstance(index, bool):
                    await ws.send_json(
                        {"type": "error", "detail": "chunk_index must be an integer"}
                    )
                    continue
                try:
                    audio = _decode_audio(msg.get("audio_b64"), settings.max_audio_bytes)
                    signals = ChunkSignals.model_validate(
                        {"transcript": msg.get("transcript"), "events": msg.get("events")}
                    )
                    chunk = AudioChunk(
                        report_id=report_id,
                        chunk_index=index,
                        scenario=report.scenario,
                        data=audio,
                        transcript=signals.transcript,
                        events=None if signals.events is None else tuple(signals.events),
                    )
                    decision = await orchestrator.process_chunk(report, chunk)
                except ValidationError:
                    await ws.send_json(
                        {"type": "error", "detail": "invalid transcript or events payload"}
                    )
                    continue
                except (ChunkRejected, ValueError) as exc:
                    await ws.send_json({"type": "error", "detail": str(exc)})
                    continue

                await _broadcast_touched(_hub.apply_route(report))
                await ws.send_json(
                    {
                        "type": "route",
                        "state": report.state,
                        "decision": decision.model_dump(mode="json"),
                    }
                )

            elif kind == "end":
                await _finalize_and_publish(orchestrator, report)
                await ws.send_json(
                    {
                        "type": "closed",
                        "state": report.state,
                        "decision": report.route.model_dump(mode="json"),
                    }
                )
                break

            else:
                await ws.send_json({"type": "error", "detail": f"unknown message: {kind}"})
    except WebSocketDisconnect:
        pass
    finally:
        # A dropped connection must not leave a provisional report in the queues.
        await _finalize_and_publish(orchestrator, report)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001 - already closed
            pass
