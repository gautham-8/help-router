"""Transcriber and detector that read the signals the caller's browser attached."""

from __future__ import annotations

from app.analyzers.interfaces import AudioChunk
from app.domain.models import AudioEvent, Transcript


class SignalMissing(RuntimeError):
    """The caller's device could not produce this signal for the chunk.

    Raised (rather than returning empty) so the orchestrator records the signal as
    missing, which a responder needs to know apart from "nothing was heard".
    """


class ClientTranscriber:
    """Returns the transcript the browser's speech recognition produced."""

    async def transcribe(self, chunk: AudioChunk) -> Transcript:
        if chunk.transcript is None:
            raise SignalMissing("no transcript from the caller's device")
        return Transcript(text=chunk.transcript, chunk_index=chunk.chunk_index)


class ClientAudioEventDetector:
    """Returns the sound events the browser's classifier detected."""

    async def detect(self, chunk: AudioChunk) -> list[AudioEvent]:
        if chunk.events is None:
            raise SignalMissing("no sound events from the caller's device")
        return list(chunk.events)
