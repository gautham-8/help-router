"""Unit tests for capture orchestration: ordering, window, failure, early finish."""

from __future__ import annotations

import asyncio

import pytest

from app.analyzers.interfaces import AnalyzerBundle, AudioChunk
from app.analyzers.mock.detector import MockAudioEventDetector
from app.analyzers.mock.transcriber import MockTranscriber
from app.analyzers.rule_router import RuleRouter
from app.domain.models import AudioEvent, Report, Transcript
from app.routing.orchestrator import CaptureOrchestrator, ChunkRejected

NUM_CHUNKS = 6


def _bundle() -> AnalyzerBundle:
    return AnalyzerBundle(MockTranscriber(), MockAudioEventDetector(), RuleRouter())


def _chunk(index: int, scenario: str | None = "kitchen-fire") -> AudioChunk:
    return AudioChunk(report_id="r", chunk_index=index, scenario=scenario)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _feed(orch: CaptureOrchestrator, report: Report, count: int) -> None:
    async def go() -> None:
        for i in range(count):
            await orch.process_chunk(report, _chunk(i))

    _run(go())


def test_first_chunk_is_provisional_and_last_is_refined() -> None:
    orch = CaptureOrchestrator(_bundle(), NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, 1)
    assert report.state == "provisional"
    assert report.route.status == "provisional"

    async def rest() -> None:
        for i in range(1, NUM_CHUNKS):
            await orch.process_chunk(report, _chunk(i))

    _run(rest())
    assert report.state == "refined"
    assert report.route.status == "refined"
    assert report.chunks_received == NUM_CHUNKS


def test_out_of_order_chunk_is_rejected_and_changes_nothing() -> None:
    orch = CaptureOrchestrator(_bundle(), NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    with pytest.raises(ChunkRejected):
        _run(orch.process_chunk(report, _chunk(3)))
    assert report.chunks_received == 0
    assert report.state == "idle"
    assert report.transcript_chunks == []


def test_duplicate_chunk_is_rejected() -> None:
    orch = CaptureOrchestrator(_bundle(), NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, 1)
    with pytest.raises(ChunkRejected):
        _run(orch.process_chunk(report, _chunk(0)))
    assert len(report.transcript_chunks) == 1
    assert len(report.events) == 1


def test_chunk_after_the_window_closed_is_rejected() -> None:
    orch = CaptureOrchestrator(_bundle(), NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, NUM_CHUNKS)
    before = report.route.model_copy(deep=True)
    with pytest.raises(ChunkRejected):
        _run(orch.process_chunk(report, _chunk(NUM_CHUNKS)))
    assert report.route == before
    assert report.state == "refined"


def test_finalize_early_marks_refined_then_closed_with_a_note() -> None:
    orch = CaptureOrchestrator(_bundle(), NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, 2)
    assert orch.finalize(report) is True
    assert report.state == "closed"
    assert report.route.status == "refined"
    assert any("ended early after 2 of 6" in n for n in report.route.notes)


def test_finalize_is_idempotent_and_ignores_empty_captures() -> None:
    orch = CaptureOrchestrator(_bundle(), NUM_CHUNKS)
    empty = Report(id="e")
    assert orch.finalize(empty) is False
    assert empty.state == "idle"

    done = Report(id="d", scenario="kitchen-fire")
    _feed(orch, done, NUM_CHUNKS)
    assert orch.finalize(done) is True
    assert orch.finalize(done) is False
    assert done.state == "closed"


class _BrokenTranscriber:
    async def transcribe(self, chunk: AudioChunk) -> Transcript:
        raise RuntimeError("speech model down")


class _BrokenDetector:
    async def detect(self, chunk: AudioChunk) -> list[AudioEvent]:
        raise RuntimeError("audio model down")


def test_failed_transcriber_still_routes_on_audio_events() -> None:
    bundle = AnalyzerBundle(_BrokenTranscriber(), MockAudioEventDetector(), RuleRouter())
    orch = CaptureOrchestrator(bundle, NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, 1)
    assert report.missing_signals == ["transcript"]
    assert "fire" in report.route.services


def test_failed_detector_still_routes_on_transcript() -> None:
    bundle = AnalyzerBundle(MockTranscriber(), _BrokenDetector(), RuleRouter())
    orch = CaptureOrchestrator(bundle, NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, 1)
    assert report.missing_signals == ["audio_events"]
    assert "fire" in report.route.services


def test_both_analyzers_failing_flags_attention_instead_of_crashing() -> None:
    bundle = AnalyzerBundle(_BrokenTranscriber(), _BrokenDetector(), RuleRouter())
    orch = CaptureOrchestrator(bundle, NUM_CHUNKS)
    report = Report(id="r", scenario="kitchen-fire")
    _feed(orch, report, 1)
    assert set(report.missing_signals) == {"transcript", "audio_events"}
    assert report.route.needs_attention is True
