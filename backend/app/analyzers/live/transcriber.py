"""Live transcriber adapter.

Wraps a real speech-to-text model. The audio bytes on the chunk are sent to the
provider and the returned text is wrapped in a :class:`Transcript`.
"""

from __future__ import annotations

from app.analyzers.interfaces import AudioChunk
from app.domain.models import Transcript


class LiveTranscriber:
    def __init__(self, api_key: str = "") -> None:
        if not api_key:
            raise RuntimeError(
                "ANALYZER_BACKEND=live needs OPENAI_API_KEY (set it in .env), or use the "
                "default mock backend (ANALYZER_BACKEND=mock)."
            )
        self._api_key = api_key

    async def transcribe(self, chunk: AudioChunk) -> Transcript:  # pragma: no cover
        # Integration point: send chunk.data to the speech-to-text model and return
        # the transcribed text. Left unimplemented to avoid a hard dependency on a
        # specific paid SDK.
        raise NotImplementedError(
            "Live transcription is a documented integration seam; wire a provider SDK "
            "here. The deterministic mock backend is the default."
        )
