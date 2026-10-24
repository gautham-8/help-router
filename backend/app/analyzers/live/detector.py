"""Live audio-event detector adapter.

Wraps a real audio-classification model that labels non-speech sounds (screams,
breaking glass, sirens, smoke alarms) with confidences.
"""

from __future__ import annotations

from app.analyzers.interfaces import AudioChunk
from app.domain.models import AudioEvent


class LiveAudioEventDetector:
    def __init__(self, url: str = "", key: str = "") -> None:
        if not url:
            raise RuntimeError(
                "ANALYZER_BACKEND=live needs AUDIO_EVENT_MODEL_URL (set it in .env), or use "
                "the default mock backend (ANALYZER_BACKEND=mock)."
            )
        self._url = url
        self._key = key

    async def detect(self, chunk: AudioChunk) -> list[AudioEvent]:  # pragma: no cover
        # Integration point: classify chunk.data and map the model's labels onto the
        # AudioEvent kinds used by the router.
        raise NotImplementedError(
            "Live audio-event detection is a documented integration seam; wire a model "
            "here. The deterministic mock backend is the default."
        )
