"""Deterministic rule-table router.

Fuses keywords (from the transcript) and audio events into a confidence per service,
carrying a prior decision forward so routing refines over the capture window.

How a step works:
  1. Start from the prior confidences, decayed by ``carry_decay`` (no fresh evidence
     means a service fades instead of staying at its peak).
  2. Add this chunk's evidence: audio events (weight x event confidence) and
     transcript keywords (whole words only; a negation such as "no" or "not" within
     the two preceding words cancels the match).
  3. Keep services at or above ``min_service_conf``, services pinned by a
     hard-guarantee event, and services committed in the prior (>= ``high_conf``).
     A service that fades out is never removed silently: a note says why.

Invariants (design properties P1-P6, P8):
  * every confidence stays within [0, 1];
  * a ``smoke_alarm`` event (>= ``guarantee_min_event_conf``) pins ``fire`` for the
    rest of the capture;
  * same (text, events, prior) -> same decision (pure function);
  * a service committed in the prior is never dropped in the next step.
"""

from __future__ import annotations

import re

from app.domain.models import ALL_SERVICES, AudioEvent, RouteDecision, Service

# Event -> (service, weight). A weight of 0 means "context only, no direct add".
_EVENT_WEIGHTS: dict[str, tuple[Service | None, float]] = {
    "smoke_alarm": ("fire", 0.6),
    "explosion": ("fire", 0.5),
    "scream": ("medical", 0.4),
    "glass_breaking": ("police", 0.4),
    "siren": (None, 0.0),
    "alarm_generic": (None, 0.0),
}

# Events that pin a service regardless of threshold (if confident enough).
_HARD_GUARANTEES: dict[str, Service] = {"smoke_alarm": "fire"}

# (pattern, service, weight). Whole words only; each pattern counts once per chunk.
_KEYWORDS: list[tuple[re.Pattern[str], Service, float]] = [
    (re.compile(r"\b(?:fires?|smoke|burning|burnt|flames?)\b"), "fire", 0.4),
    (
        re.compile(
            r"\b(?:hurt|bleed(?:s|ing)?|blood|bloody|unconscious|unresponsive|injured"
            r"|injuries|wound(?:s|ed)?|bullets?|shot|stabbed|not breathing|heart attack"
            r"|chest pain|overdos(?:e|ed)|ambulances?|medics?)\b"
        ),
        "medical",
        0.5,
    ),
    (
        re.compile(
            r"\b(?:break[- ]?in|breaking in|broke in|attacker|guns?|gunshots?|bullets?"
            r"|shot|shots fired|shooting|shooter|robbery|robbed|stolen|intruder|stabbed"
            r"|police)\b"
        ),
        "police",
        0.5,
    ),
    (re.compile(r"\b(?:crash(?:ed)?|accident|collision)\b"), "medical", 0.3),
]

_WORD = re.compile(r"[a-z']+")
# Negation only reaches back within a clause: punctuation or these words end it.
_CLAUSE_BREAK = re.compile(r"[.,;:!?]|\b(?:but|and|then|so)\b")
_NEGATION_WINDOW = 3
_NEGATIONS = frozenset(
    {
        "no",
        "nobody",
        "not",
        "never",
        "without",
        "nothing",
        "isn't",
        "wasn't",
        "aren't",
        "weren't",
        "don't",
        "doesn't",
        "didn't",
        "hasn't",
        "haven't",
    }
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _has_unnegated_match(pattern: re.Pattern[str], text: str) -> bool:
    """True if ``pattern`` matches somewhere not negated.

    A match is negated when a negation word appears in the up-to-three words before it
    within the same clause. This is a heuristic and deliberately conservative: for an
    emergency router a missed fire costs more than a false alarm, so "no, help, fire"
    still routes (the comma ends the clause).
    """
    for match in pattern.finditer(text):
        clause = _CLAUSE_BREAK.split(text[: match.start()])[-1]
        preceding = _WORD.findall(clause)[-_NEGATION_WINDOW:]
        if not any(word in _NEGATIONS for word in preceding):
            return True
    return False


class RuleRouter:
    """Pure, deterministic router over a fixed rule table."""

    def __init__(
        self,
        min_service_conf: float = 0.3,
        high_conf: float = 0.7,
        carry_decay: float = 0.85,
        guarantee_min_event_conf: float = 0.5,
    ) -> None:
        for name, value in (
            ("min_service_conf", min_service_conf),
            ("high_conf", high_conf),
            ("guarantee_min_event_conf", guarantee_min_event_conf),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1], got {value}")
        if not 0.0 < carry_decay <= 1.0:
            raise ValueError(f"carry_decay must be within (0, 1], got {carry_decay}")
        self.min_service_conf = min_service_conf
        self.high_conf = high_conf
        self.carry_decay = carry_decay
        self.guarantee_min_event_conf = guarantee_min_event_conf

    def route(
        self,
        transcript_text: str,
        events: list[AudioEvent],
        prior: RouteDecision | None,
        status: str = "provisional",
    ) -> RouteDecision:
        # 1. Carry the prior forward, decayed.
        scores: dict[Service, float] = {}
        pinned: set[Service] = set()
        if prior is not None:
            scores = {s: _clamp(c * self.carry_decay) for s, c in prior.services.items()}
            pinned = set(prior.pinned)

        # 2a. Evidence from audio events.
        for event in events:
            service, weight = _EVENT_WEIGHTS.get(event.kind, (None, 0.0))
            if service is not None and weight > 0.0:
                scores[service] = _clamp(scores.get(service, 0.0) + weight * event.confidence)
            hard = _HARD_GUARANTEES.get(event.kind)
            if hard is not None and event.confidence >= self.guarantee_min_event_conf:
                pinned.add(hard)

        # 2b. Evidence from transcript keywords.
        text = transcript_text.lower().replace("\u2019", "'")
        for pattern, service, weight in _KEYWORDS:
            if _has_unnegated_match(pattern, text):
                scores[service] = _clamp(scores.get(service, 0.0) + weight)

        # 3. Decide which services survive.
        notes: list[str] = list(prior.notes) if prior else []

        def add_note(note: str) -> None:
            if note not in notes:
                notes.append(note)

        result: dict[Service, float] = {}
        for service in ALL_SERVICES:
            conf = _clamp(scores.get(service, 0.0))
            in_prior = prior is not None and service in prior.services
            prior_conf = prior.services[service] if prior is not None and in_prior else 0.0
            committed = in_prior and prior_conf >= self.high_conf

            if service in pinned:
                result[service] = max(conf, self.min_service_conf)
            elif conf >= self.min_service_conf:
                result[service] = conf
            elif committed:
                # Keep a committed service visible; tell the responder it weakened.
                result[service] = conf
                add_note(f"{service} downgraded {prior_conf:.2f}->{conf:.2f}")
            elif in_prior:
                add_note(f"{service} dropped: evidence faded ({prior_conf:.2f}->{conf:.2f})")

        return RouteDecision(
            services=result,
            status="refined" if status == "refined" else "provisional",
            needs_attention=len(result) == 0,
            notes=notes,
            pinned=sorted(pinned),
        )
