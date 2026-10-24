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

from app.domain.models import ALL_SERVICES, AudioEvent, RouteDecision, RouteStatus, Service

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

# ---------------------------------------------------------------------------
# Keyword vocabulary.
#
# Each service has a big list of TERMS — real ways people describe an emergency. A term
# may be a word or a short phrase. The regex matches whole words only (so "gun" never
# fires inside "begun"), and the engine already handles negation ("no fire" does not
# route). Common inflections are written out as alternations in the term itself
# (e.g. "bleeding|bleeds|bled") rather than with fragile stemming.
#
# To add coverage: drop a term into the right list. No other code changes. Keep terms
# lowercase; phrases match with normal spacing.
# ---------------------------------------------------------------------------

_FIRE_TERMS: list[str] = [
    # fire itself
    "fire", "fires", "on fire", "catching fire", "caught fire", "caught on fire",
    "house fire", "kitchen fire", "car fire", "grease fire", "electrical fire",
    "wildfire", "brush fire", "forest fire", "building fire", "apartment fire",
    # smoke / flames / heat
    "smoke", "smoky", "smoke everywhere", "thick smoke", "black smoke", "smell smoke",
    "smell of smoke", "smells like smoke", "smoke alarm", "fire alarm",
    "flame", "flames", "flames everywhere", "up in flames", "engulfed",
    "burning", "burnt", "burned", "it's burning", "something's burning", "stuff burning",
    "blaze", "blazing", "inferno", "scorched", "singed",
    # cause / spread
    "explosion", "explosions", "blew up", "blown up", "exploded", "gas leak",
    "gas smell", "smell gas", "propane", "sparks", "sparking", "short circuit",
    "wires sparking", "stove on fire", "oven on fire", "oil caught fire",
    "candle fell", "fireworks", "bonfire out of control", "spreading fire",
    "fire spreading", "smoke inhalation", "can't see through smoke",
    "building's smoking", "roof on fire", "trapped by fire", "smoke filling the room",
    "fire extinguisher", "need the fire department", "call the fire brigade",
]

_MEDICAL_TERMS: list[str] = [
    # injury / bleeding
    "hurt", "injured", "injury", "injuries", "wound", "wounds", "wounded",
    "bleeding", "bleeds", "bled", "blood", "bloody", "losing blood", "lots of blood",
    "deep cut", "gash", "laceration", "severed", "amputated", "crushed", "broken bone",
    "broken leg", "broken arm", "fracture", "compound fracture", "head injury",
    "concussion", "internal bleeding", "bruised badly", "impaled",
    "bullet", "bullets", "bullet wound", "gunshot wound", "shot in the", "been shot",
    "shot", "got shot", "shot him", "shot her", "shot me",
    "stab wound", "knife wound",
    # breathing / cardiac / collapse
    "not breathing", "can't breathe", "cant breathe", "trouble breathing",
    "struggling to breathe", "gasping", "choking", "choked", "suffocating",
    "heart attack", "cardiac arrest", "chest pain", "chest pains", "clutching chest",
    "stroke", "seizure", "convulsing", "fainted", "passed out", "collapsed",
    "unconscious", "unresponsive", "won't wake up", "not responding", "no pulse",
    # drowning / environmental
    "drowning", "drowned", "underwater", "went under", "can't swim", "pulled under",
    "water over my head", "water over the head", "over my head", "head under water",
    "can't keep my head up", "going under", "sinking",
    "falling from", "fell from", "fell off", "big fall",
    "hypothermia", "heat stroke", "frostbite", "electrocuted", "electric shock",
    # illness / poisoning / obstetric
    "overdose", "overdosed", "poisoned", "poisoning", "allergic reaction",
    "anaphylaxis", "anaphylactic", "can't feel my legs", "paralyzed", "numb",
    "diabetic", "insulin", "going into shock", "in shock", "vomiting blood",
    "coughing blood", "pregnant", "in labor", "in labour", "giving birth",
    "water broke", "baby coming", "miscarriage",
    # dying / help asks
    "dying", "he's dying", "she's dying", "going to die", "about to die",
    "need an ambulance", "call an ambulance", "need a medic", "need paramedics",
    "someone's hurt", "badly hurt", "critically injured", "life threatening",
]

_POLICE_TERMS: list[str] = [
    # intrusion / theft
    "break in", "break-in", "breaking in", "broke in", "broke into", "broken in",
    "broken into", "breaking into", "home invasion",
    "someone's in the house", "someone in my house", "intruder", "prowler",
    "burglar", "burglary", "robbery", "robbed", "being robbed", "mugged", "mugging",
    "stolen", "theft", "carjacking", "carjacked", "trespasser", "trespassing",
    "someone following me", "being followed", "stalker", "stalking", "peeping",
    # weapons / violence
    "gun", "guns", "gunman", "gunshot", "gunshots", "shots fired", "shooting",
    "shooter", "active shooter", "armed", "he has a weapon", "knife", "machete",
    "stabbed", "stabbing", "being stabbed", "bullet", "bullets", "shot", "shot at",
    "attack", "attacked", "being attacked", "attacker", "assault", "assaulted",
    "beaten", "beating", "jumped", "fight", "fighting", "brawl",
    "domestic violence", "he's hitting me", "she's hitting me", "being hit",
    "strangling", "choking me", "held at gunpoint", "held at knifepoint",
    "threatening me", "threatened", "threats", "death threat",
    # abduction / hostage / killing
    "kidnapped", "kidnapping", "abducted", "taken", "hostage", "held captive",
    "tied up", "locked in", "won't let me leave", "trafficking",
    "kill", "killing", "killed", "going to kill", "trying to kill me",
    "murder", "murdered", "murdering", "slaughter", "slaughtered",
    "someone's dead", "dead body", "shot someone", "stabbed someone",
    # drugs / disorder / asking for police
    "drug deal", "dealing drugs", "vandalism", "vandalizing", "riot", "looting",
    "hit and run", "drunk driver", "road rage", "someone dangerous",
    "call the police", "need the police", "need cops", "send police",
]

# crash straddles police + medical; keep it as a lighter medical signal like before
_CRASH_TERMS: list[str] = [
    "crash", "crashed", "car crash", "accident", "car accident", "collision",
    "wreck", "pile up", "pileup", "rollover", "flipped the car", "hit by a car",
    "ran off the road", "motorcycle accident",
]


def _compile_terms(terms: list[str]) -> re.Pattern[str]:
    """Compile a term list into one whole-word, case-insensitive alternation.

    Longer phrases are tried first so "chest pain" wins over a stray "pain" fragment.
    Spaces in a term match one or more spaces so "break  in" still matches.
    """
    ordered = sorted(set(terms), key=len, reverse=True)
    parts = [re.escape(term).replace(r"\ ", r"\s+") for term in ordered]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b")


# (pattern, service, weight). Whole words only; each pattern counts once per chunk.
_KEYWORDS: list[tuple[re.Pattern[str], Service, float]] = [
    (_compile_terms(_FIRE_TERMS), "fire", 0.5),
    (_compile_terms(_MEDICAL_TERMS), "medical", 0.5),
    (_compile_terms(_POLICE_TERMS), "police", 0.5),
    (_compile_terms(_CRASH_TERMS), "medical", 0.3),
]

_WORD = re.compile(r"[a-z0-9']+")
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
        status: RouteStatus = "provisional",
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
