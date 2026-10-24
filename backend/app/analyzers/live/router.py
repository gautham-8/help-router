"""Live router adapter.

A production router would prompt an LLM to fuse transcript + events into the
:class:`RouteDecision` schema. Until that is wired, this adapter delegates to the same
deterministic rule router the other backends use. Swap ``route`` for an LLM call to
upgrade.
"""

from __future__ import annotations

from app.analyzers.rule_router import RuleRouter
from app.domain.models import AudioEvent, RouteDecision, RouteStatus


class LiveRouter:
    def __init__(
        self,
        min_service_conf: float = 0.3,
        high_conf: float = 0.7,
        carry_decay: float = 0.85,
        guarantee_min_event_conf: float = 0.5,
    ) -> None:
        # Integration point: initialise an LLM client here. For now reuse the
        # rule-table fusion so the same invariants (P1-P11) still hold.
        self._fallback = RuleRouter(
            min_service_conf=min_service_conf,
            high_conf=high_conf,
            carry_decay=carry_decay,
            guarantee_min_event_conf=guarantee_min_event_conf,
        )

    def route(
        self,
        transcript_text: str,
        events: list[AudioEvent],
        prior: RouteDecision | None,
        status: RouteStatus = "provisional",
    ) -> RouteDecision:
        return self._fallback.route(transcript_text, events, prior, status)
