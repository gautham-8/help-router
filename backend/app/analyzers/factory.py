"""Selects the analyzer backend from configuration.

The rest of the app calls :func:`get_analyzers` and receives an
:class:`AnalyzerBundle` of protocol-typed objects. Switching ``ANALYZER_BACKEND`` changes
only the signal source; the rule router and everything downstream are identical.

Two rules worth knowing:
  * A report created with a demo ``scenario`` always gets the scripted mock analyzers,
    whatever the configured backend. That keeps demos and tests deterministic.
  * Building the bundle is also where a misconfigured ``live`` backend (missing keys)
    fails, so the API checks it when a report is created rather than mid-stream.
"""

from __future__ import annotations

from app.config import Settings, get_settings

from .interfaces import AnalyzerBundle
from .rule_router import RuleRouter


def _router(settings: Settings) -> RuleRouter:
    return RuleRouter(
        min_service_conf=settings.min_service_conf,
        high_conf=settings.high_conf,
        carry_decay=settings.carry_decay,
        guarantee_min_event_conf=settings.guarantee_min_event_conf,
    )


def build_analyzers(settings: Settings, scenario: str | None = None) -> AnalyzerBundle:
    """Construct the analyzer bundle for the configured backend (or a demo scenario)."""
    backend = "mock" if scenario is not None else settings.analyzer_backend

    if backend == "mock":
        from .mock.detector import MockAudioEventDetector
        from .mock.transcriber import MockTranscriber

        return AnalyzerBundle(MockTranscriber(), MockAudioEventDetector(), _router(settings))

    if backend == "browser":
        from .browser.signals import ClientAudioEventDetector, ClientTranscriber

        return AnalyzerBundle(ClientTranscriber(), ClientAudioEventDetector(), _router(settings))

    if backend == "live":
        from .live.detector import LiveAudioEventDetector
        from .live.transcriber import LiveTranscriber

        return AnalyzerBundle(
            transcriber=LiveTranscriber(api_key=settings.openai_api_key),
            detector=LiveAudioEventDetector(
                url=settings.audio_event_model_url, key=settings.audio_event_model_key
            ),
            router=_router(settings),
        )

    raise RuntimeError(f"unknown ANALYZER_BACKEND: {backend}")


def get_analyzers(scenario: str | None = None) -> AnalyzerBundle:
    """Build analyzers using the process-wide settings."""
    return build_analyzers(get_settings(), scenario)
