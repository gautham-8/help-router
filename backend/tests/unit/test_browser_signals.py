"""Unit tests for the browser-signal analyzers and the factory's backend rules."""

from __future__ import annotations

import asyncio

import pytest

from app.analyzers.browser.signals import (
    ClientAudioEventDetector,
    ClientTranscriber,
    SignalMissing,
)
from app.analyzers.factory import build_analyzers
from app.analyzers.interfaces import AudioChunk
from app.analyzers.mock.detector import MockAudioEventDetector
from app.config import Settings
from app.domain.models import AudioEvent, Report
from app.routing.orchestrator import CaptureOrchestrator


def run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_transcriber_returns_what_the_device_heard() -> None:
    chunk = AudioChunk("r", 2, transcript="help me")
    transcript = run(ClientTranscriber().transcribe(chunk))
    assert transcript.text == "help me"
    assert transcript.chunk_index == 2


def test_silence_is_not_the_same_as_a_missing_signal() -> None:
    assert run(ClientTranscriber().transcribe(AudioChunk("r", 0, transcript=""))).text == ""
    assert run(ClientAudioEventDetector().detect(AudioChunk("r", 0, events=()))) == []


def test_missing_signals_raise() -> None:
    with pytest.raises(SignalMissing):
        run(ClientTranscriber().transcribe(AudioChunk("r", 0)))
    with pytest.raises(SignalMissing):
        run(ClientAudioEventDetector().detect(AudioChunk("r", 0)))


def test_detector_returns_the_devices_events() -> None:
    events = (AudioEvent(kind="siren", confidence=0.4), AudioEvent(kind="scream", confidence=0.9))
    assert run(ClientAudioEventDetector().detect(AudioChunk("r", 0, events=events))) == list(events)


def test_orchestrator_records_missing_signals_by_name() -> None:
    settings = Settings(_env_file=None, analyzer_backend="browser")  # type: ignore[call-arg]
    orchestrator = CaptureOrchestrator(build_analyzers(settings), 6)
    report = Report(id="r")
    run(
        orchestrator.process_chunk(
            report, AudioChunk("r", 0, events=(AudioEvent(kind="smoke_alarm", confidence=0.9),))
        )
    )
    assert report.missing_signals == ["transcript"]
    assert "fire" in report.route.services


def test_factory_picks_the_configured_backend() -> None:
    browser = build_analyzers(Settings(_env_file=None, analyzer_backend="browser"))  # type: ignore[call-arg]
    assert isinstance(browser.transcriber, ClientTranscriber)
    mock = build_analyzers(Settings(_env_file=None, analyzer_backend="mock"))  # type: ignore[call-arg]
    assert isinstance(mock.detector, MockAudioEventDetector)


def test_a_scenario_always_gets_the_scripted_analyzers() -> None:
    for backend in ("browser", "mock", "live"):
        settings = Settings(_env_file=None, analyzer_backend=backend)  # type: ignore[call-arg]
        bundle = build_analyzers(settings, scenario="kitchen-fire")
        assert isinstance(bundle.detector, MockAudioEventDetector), backend


def test_live_without_keys_raises_a_clear_error() -> None:
    settings = Settings(_env_file=None, analyzer_backend="live")  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_analyzers(settings)
