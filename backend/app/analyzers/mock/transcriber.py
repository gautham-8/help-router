"""Deterministic mock transcriber: returns scripted text per scenario chunk."""

from __future__ import annotations

from app.analyzers.interfaces import AudioChunk
from app.domain.models import Transcript

from .scenarios import chunk_data


class MockTranscriber:
    """Returns the scripted transcript for ``(scenario, chunk_index)``."""

    async def transcribe(self, chunk: AudioChunk) -> Transcript:
        text = ""
        if chunk.scenario is not None:
            text = chunk_data(chunk.scenario, chunk.chunk_index).get("transcript", "")
        return Transcript(text=text, chunk_index=chunk.chunk_index)
