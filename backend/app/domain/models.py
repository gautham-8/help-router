"""Core domain models shared across capture, analysis, routing, and dispatch.

These are the shared vocabulary of Help Router. Routing never collapses uncertainty
to a single service too early: a :class:`RouteDecision` carries a confidence per
service, and several services may apply at once.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# --- Enumerations / literals -------------------------------------------------

Service = Literal["police", "fire", "medical"]
ALL_SERVICES: tuple[Service, ...] = ("police", "fire", "medical")

# A dispatch queue is one per service, plus "triage": where reports the system could not
# classify wait for a human to send them to a service or dismiss them.
QueueName = Literal["police", "fire", "medical", "triage"]
ALL_QUEUES: tuple[QueueName, ...] = (*ALL_SERVICES, "triage")

AudioEventKind = Literal[
    "scream",
    "glass_breaking",
    "siren",
    "smoke_alarm",
    "explosion",
    "alarm_generic",
]

RouteStatus = Literal["provisional", "refined"]

# Forward-only capture/route lifecycle.
CaptureState = Literal["idle", "listening", "provisional", "refined", "closed"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- Signals -----------------------------------------------------------------


class AudioEvent(BaseModel):
    """A detected non-speech sound with a confidence in ``[0, 1]``."""

    kind: AudioEventKind
    confidence: float = Field(ge=0.0, le=1.0)


class Transcript(BaseModel):
    """Transcribed text for a single audio chunk."""

    text: str
    chunk_index: int = Field(ge=0)


# --- Routing -----------------------------------------------------------------


class RouteDecision(BaseModel):
    """A set of services, each with a confidence, plus routing status.

    ``services`` only contains services that are being routed; a confidence of 0 is
    not stored. ``needs_attention`` is true when nothing is clearly indicated.
    """

    services: dict[Service, float] = Field(default_factory=dict)
    status: RouteStatus = "provisional"
    needs_attention: bool = False
    notes: list[str] = Field(default_factory=list)
    # Services forced in by a hard-guarantee event (e.g. smoke_alarm -> fire). Once
    # pinned, a service stays routed for the rest of the capture.
    pinned: list[Service] = Field(default_factory=list)

    @field_validator("services")
    @classmethod
    def _confidences_in_range(cls, value: dict[str, float]) -> dict[str, float]:
        for service, conf in value.items():
            if not 0.0 <= conf <= 1.0:
                raise ValueError(f"confidence for {service} out of range: {conf}")
        return value

    def indicated_services(self, min_conf: float) -> list[Service]:
        """Services at or above ``min_conf``, in canonical order."""
        return [s for s in ALL_SERVICES if self.services.get(s, 0.0) >= min_conf]


# --- Location & report -------------------------------------------------------


class Location(BaseModel):
    """Caller location; ``known`` is false when geolocation was unavailable."""

    lat: float | None = None
    lon: float | None = None
    accuracy_m: float | None = None
    known: bool = False

    @classmethod
    def unknown(cls) -> Location:
        return cls(known=False)


class Report(BaseModel):
    """A capture session with its signals, route decision, and location."""

    id: str
    created_at: datetime = Field(default_factory=_utcnow)
    location: Location = Field(default_factory=Location.unknown)
    transcript_chunks: list[Transcript] = Field(default_factory=list)
    events: list[AudioEvent] = Field(default_factory=list)
    route: RouteDecision = Field(default_factory=RouteDecision)
    state: CaptureState = "idle"
    scenario: str | None = None
    missing_signals: list[str] = Field(default_factory=list)
    # Number of chunks accepted so far; the next expected chunk_index.
    chunks_received: int = Field(default=0, ge=0)


# --- Dispatch ----------------------------------------------------------------


class DispatchStatus(BaseModel):
    """Per-(report, service) human decision. Confirmed is the only path to dispatch."""

    report_id: str
    service: QueueName
    confirmed: bool = False
    rejected: bool = False
    responder: str | None = None
    decided_at: datetime | None = None
