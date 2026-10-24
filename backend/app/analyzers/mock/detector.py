"""Deterministic mock audio-event detector: scripted events per scenario chunk."""

from __future__ import annotations

from app.analyzers.interfaces import AudioChunk
from app.domain.models import AudioEvent

from .scenarios import chunk_data


class MockAudioEventDetector:
    """Returns the scripted audio events for ``(scenario, chunk_index)``."""

    async def detect(self, chunk: AudioChunk) -> list[AudioEvent]:
        if chunk.scenario is None:
            return []
        raw = chunk_data(chunk.scenario, chunk.chunk_index).get("events", [])
        return [AudioEvent(kind=e["kind"], confidence=e["confidence"]) for e in raw]
