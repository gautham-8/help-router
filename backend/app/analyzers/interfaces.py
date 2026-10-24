"""Analyzer protocols — the only contract the rest of the app depends on.

Routing, dispatch, and the WebSocket layer import these protocols, never a concrete
model or vendor SDK. Adding a new vendor means adding one new implementation of a
protocol and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.models import AudioEvent, RouteDecision, RouteStatus, Transcript


@dataclass(frozen=True)
class AudioChunk:
    """One slice of captured audio, plus whatever the caller's device already worked out.

    * ``mock`` (demo scenarios) ignores the audio: the chunk is identified by its
      scenario and index.
    * ``browser`` uses ``transcript`` and ``events``, which the caller's browser produced
      on the device (speech recognition and a sound classifier). ``None`` means that
      signal was unavailable, which is different from "heard nothing" (``""`` / ``()``).
      These values are client-asserted and unauthenticated.
    * ``live`` uses ``data`` (server-side models).
    """

    report_id: str
    chunk_index: int
    scenario: str | None = None
    data: bytes = b""
    transcript: str | None = None
    events: tuple[AudioEvent, ...] | None = None


@runtime_checkable
class Transcriber(Protocol):
    """Turns an audio chunk into text."""

    async def transcribe(self, chunk: AudioChunk) -> Transcript: ...


@runtime_checkable
class AudioEventDetector(Protocol):
    """Detects non-speech sounds in an audio chunk."""

    async def detect(self, chunk: AudioChunk) -> list[AudioEvent]: ...


@runtime_checkable
class Router(Protocol):
    """Fuses transcript text and audio events into a route decision.

    ``prior`` carries the previous decision so routing can refine over time. The
    mock implementation is a pure function: same inputs, same output.
    """

    def route(
        self,
        transcript_text: str,
        events: list[AudioEvent],
        prior: RouteDecision | None,
        status: RouteStatus,
    ) -> RouteDecision: ...


@dataclass(frozen=True)
class AnalyzerBundle:
    """The three analyzers for a given backend, resolved together."""

    transcriber: Transcriber
    detector: AudioEventDetector
    router: Router
