"""Drives a report through analysis and refinement over the capture window.

Per chunk: transcribe + detect (tolerating per-signal failure, Requirement 2.5),
then route carrying the prior decision forward. The first chunk yields a
``provisional`` decision; the final chunk yields a ``refined`` one. State advances
only forward via the state machine.

Chunks must arrive in order, exactly once, while the window is open. Anything else is
rejected with :class:`ChunkRejected` and leaves the report untouched.
"""

from __future__ import annotations

from app.analyzers.interfaces import AnalyzerBundle, AudioChunk
from app.domain import state
from app.domain.models import AudioEvent, Report, RouteDecision, Transcript


class ChunkRejected(ValueError):
    """Raised when a chunk is out of order, duplicated, or arrives after the window."""


class CaptureOrchestrator:
    """Stateless-per-call orchestration of analyze -> route for a report."""

    def __init__(self, analyzers: AnalyzerBundle, num_chunks: int) -> None:
        self._analyzers = analyzers
        self._num_chunks = num_chunks

    async def process_chunk(self, report: Report, chunk: AudioChunk) -> RouteDecision:
        """Analyze one chunk and update the report's route decision in place."""
        if report.state in ("refined", "closed"):
            raise ChunkRejected("the capture window is already closed")
        if chunk.chunk_index != report.chunks_received:
            raise ChunkRejected(f"expected chunk {report.chunks_received}, got {chunk.chunk_index}")

        had_prior = report.chunks_received > 0
        report.chunks_received += 1

        if report.state == "idle":
            report.state = state.transition(report.state, "listening")

        # Transcribe (tolerate failure).
        text = ""
        try:
            transcript: Transcript = await self._analyzers.transcriber.transcribe(chunk)
            report.transcript_chunks.append(transcript)
            text = transcript.text
        except Exception:  # noqa: BLE001 - degrade gracefully per Req 2.5
            self._mark_missing(report, "transcript")

        # Detect audio events (tolerate failure).
        events: list[AudioEvent] = []
        try:
            events = await self._analyzers.detector.detect(chunk)
            report.events.extend(events)
        except Exception:  # noqa: BLE001
            self._mark_missing(report, "audio_events")

        is_final = chunk.chunk_index >= self._num_chunks - 1
        prior = report.route if had_prior else None
        decision = self._analyzers.router.route(
            text, events, prior, "refined" if is_final else "provisional"
        )
        report.route = decision

        # First decision -> provisional; final chunk -> refined.
        if report.state == "listening":
            report.state = state.transition(report.state, "provisional")
        if is_final and report.state == "provisional":
            report.state = state.transition(report.state, "refined")

        return decision

    def finalize(self, report: Report) -> bool:
        """End a capture: provisional -> refined (if cut short) -> closed.

        Called on an explicit ``end`` and when the caller's connection drops, so a
        report never sits in a responder's queue marked provisional forever.
        Returns True if the report changed.
        """
        changed = False
        if report.state == "provisional":
            notes = [
                *report.route.notes,
                f"capture ended early after {report.chunks_received} of "
                f"{self._num_chunks} chunks",
            ]
            report.route = report.route.model_copy(update={"status": "refined", "notes": notes})
            report.state = state.transition(report.state, "refined")
            changed = True
        if report.state == "refined":
            report.state = state.transition(report.state, "closed")
            changed = True
        return changed

    @staticmethod
    def _mark_missing(report: Report, signal: str) -> None:
        if signal not in report.missing_signals:
            report.missing_signals.append(signal)
