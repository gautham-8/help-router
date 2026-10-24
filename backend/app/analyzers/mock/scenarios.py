"""Loader for scripted demo scenarios.

Each scenario JSON file scripts, per chunk index, a transcript line and a list of
audio events. Scenarios drive the deterministic mock backend and seed the demo.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCENARIO_DIR = Path(__file__).parent / "scenarios"


class ScenarioError(KeyError):
    """Raised when a scenario or chunk index is not found."""


@lru_cache
def _load_all() -> dict[str, dict[str, Any]]:
    scenarios: dict[str, dict[str, Any]] = {}
    for path in sorted(_SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios[data["id"]] = data
    return scenarios


def list_scenarios() -> list[dict[str, str]]:
    """Return ``[{id, label, summary}]`` for every available scenario."""
    return [
        {"id": s["id"], "label": s["label"], "summary": s.get("summary", "")}
        for s in _load_all().values()
    ]


def get_scenario(scenario_id: str) -> dict[str, Any]:
    scenarios = _load_all()
    if scenario_id not in scenarios:
        raise ScenarioError(f"unknown scenario: {scenario_id}")
    return scenarios[scenario_id]


def chunk_data(scenario_id: str, chunk_index: int) -> dict[str, Any]:
    """Return the scripted ``{transcript, events}`` for a scenario chunk.

    Indices past the scripted end repeat the final chunk (so a longer capture window
    still behaves deterministically).
    """
    scenario = get_scenario(scenario_id)
    chunks: list[dict[str, Any]] = scenario["chunks"]
    if not chunks:
        return {"transcript": "", "events": []}
    index = min(chunk_index, len(chunks) - 1)
    return chunks[index]
