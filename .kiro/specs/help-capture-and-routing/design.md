# Design: Help Capture and Routing

## Overview

Help Router captures 60 seconds of audio (in ~10 s chunks) plus location from a
caller's phone, analyzes each chunk with three pluggable analyzers, fuses the signals
into a route decision (a set of services, each with a confidence), emits that route
provisionally and refines it over the window, and places the report into the matching
dispatch queue(s) where a human responder confirms every dispatch. No real emergency
service is ever contacted.

```
 Caller's device                                    Server
 ───────────────                                    ──────
 mic ─▶ MediaRecorder ─▶ 10 s chunk ──┬─▶ speech-to-text (Web Speech API) ─ text ─┐
                                      └─▶ YAMNet via TF.js (sound events) ─────────┤
                                                                                   ▼
                          WebSocket: {transcript, events} per chunk ─▶ FastAPI capture endpoint
                                                                                   │
                                                    ┌──────────────────────────────┴──────┐
                                                    │ Analyzer backend (factory):         │
                                                    │  browser (default) | mock | live    │
                                                    │  Transcriber · AudioEventDetector   │
                                                    │  Router (rule table)                │
                                                    └──────────────────┬──────────────────┘
                                                                       │ RouteDecision
                                                                       ▼
                              Fan-out → Police / Fire / Medical queues (or Triage if none)
                                                                       │ WebSocket push
                                                                       ▼
                              Dispatch Dashboard ── responder confirms / rejects / triages
```

Only text and sound labels leave the device; no audio is uploaded in the default mode.
`mock` plays a scripted scenario (demo mode and tests). `live` is the seam for server-side
models and is not wired to a provider yet.

## Components

### 1. Domain models (`backend/app/domain/models.py`)

```python
Service = Literal["police", "fire", "medical"]
RouteStatus = Literal["provisional", "refined"]
CaptureState = Literal["idle", "listening", "provisional", "refined", "closed"]

class AudioEvent(BaseModel):
    kind: Literal["scream", "glass_breaking", "siren", "smoke_alarm", "explosion", "alarm_generic"]
    confidence: float  # [0, 1]

class Transcript(BaseModel):
    text: str
    chunk_index: int

class RouteDecision(BaseModel):
    services: dict[Service, float]   # confidence per service, each in [0, 1]
    status: RouteStatus
    needs_attention: bool            # true when nothing is clearly indicated
    notes: list[str] = []            # e.g. downgrade flags for the responder

class Location(BaseModel):
    lat: float | None
    lon: float | None
    accuracy_m: float | None
    known: bool

class Report(BaseModel):
    id: str
    created_at: datetime
    location: Location
    transcript_chunks: list[Transcript]
    events: list[AudioEvent]
    route: RouteDecision
    state: CaptureState

class DispatchStatus(BaseModel):
    report_id: str
    service: Service
    confirmed: bool
    rejected: bool
    responder: str | None
    decided_at: datetime | None
```

### 2. The analyzer seam (`backend/app/analyzers/`)

Protocols in `interfaces.py`:

```python
class Transcriber(Protocol):
    async def transcribe(self, chunk: AudioChunk) -> Transcript: ...

class AudioEventDetector(Protocol):
    async def detect(self, chunk: AudioChunk) -> list[AudioEvent]: ...

class Router(Protocol):
    def route(self, transcript_text: str, events: list[AudioEvent],
              prior: RouteDecision | None) -> RouteDecision: ...
```

`factory.py` reads `ANALYZER_BACKEND` (default `browser`; a report with a scenario always gets `mock`) and returns a bundle of the
three implementations. Routing/dispatch/WebSocket code imports only the protocols.

#### Browser backend (`analyzers/browser/`, DEFAULT)
- `ClientTranscriber` / `ClientAudioEventDetector` return the transcript and sound events
  the device attached to the chunk. `None` (the device could not produce it) raises
  `SignalMissing`, which the orchestrator records in `report.missing_signals`; `""` / `[]`
  means "heard nothing" and is not an error.
- Routing uses the same rule router as every other backend.
- Signals are client-asserted and unauthenticated: a hostile client can claim a smoke
  alarm. A human confirming every dispatch is the control, and the dashboard shows the
  evidence. They are validated and bounded (`ChunkSignals`).

#### Mock backend (`analyzers/mock/`, demo mode and tests)
- A report created with a `scenario` always gets these analyzers, whatever
  `ANALYZER_BACKEND` is, so demos and tests stay deterministic.
- `MockTranscriber`: returns the scripted transcript for `(scenario, chunk_index)`.
- `MockAudioEventDetector`: returns the scripted events for `(scenario, chunk_index)`.
- `MockRouter`: pure function over a fixed rule table (below). No randomness.
- `scenarios/*.json`: each scenario scripts, per chunk index 0..5, a transcript line
  and a list of `{kind, confidence}` events.

#### Live backend (`analyzers/live/`, behind `.env`)
- `LiveTranscriber`: speech-to-text model.
- `LiveAudioEventDetector`: audio-classification model.
- `LiveRouter`: LLM prompted to output the same `RouteDecision` schema.
- Selecting `live` changes only the signal source; all downstream code is identical.

### 3. Routing rule table (mock router)

Deterministic fusion of keywords and events into service confidences, clamped to
`[0, 1]`. Event contributions are `weight × event confidence`; keyword contributions are
the flat weight, once per pattern per chunk.

| Signal | Contributes to | Weight |
|--------|----------------|--------|
| event `smoke_alarm` | fire | +0.6 (and pins `fire`, see below) |
| event `explosion` | fire | +0.5 |
| keyword fire/smoke/burning/flames | fire | +0.4 |
| event `scream` | medical | +0.4 |
| keyword hurt/bleeding/unconscious/injured/ambulance/medic | medical | +0.5 |
| keyword crash/accident/collision | medical | +0.3 |
| event `glass_breaking` | police | +0.4 |
| keyword break-in/breaking in/attacker/gun/robbery/stolen/intruder/police | police | +0.5 |
| event `siren`, `alarm_generic` | (context only, no direct add) | 0 |

Rules, applied per chunk in this order:
1. **Decay.** Start from `prior.services × CARRY_DECAY` (default 0.85), else empty. A
   service with no fresh evidence fades instead of staying at its peak.
2. **Add evidence** from this chunk's events and keywords; clamp to `[0, 1]`.
3. **Whole words only.** Keywords match whole words ("begun" does not contain "gun").
4. **Narrow negation.** A keyword preceded by a negation word ("no", "not", "never",
   "without", "nobody", "doesn't", …) within the previous three words *of the same
   clause* does not count. Punctuation and "but/and/then/so" end a clause, so "no, help,
   there's a fire" still routes. This is a heuristic, deliberately conservative: a missed
   emergency costs more than a false alarm.
5. **Pinning.** A `smoke_alarm` event with confidence ≥ `GUARANTEE_MIN_EVENT_CONF`
   (default 0.5) adds `fire` to `RouteDecision.pinned`. Pinned services are always in the
   result (at least `MIN_SERVICE_CONF`) for the rest of the capture, because `pinned` is
   carried forward from the prior decision. A faint alarm does not pin.
6. **Threshold.** A service is routed if its confidence ≥ `MIN_SERVICE_CONF` (default
   0.3). `needs_attention` is true exactly when nothing is routed.
7. **Monotonic commitment.** A service with prior confidence ≥ `HIGH_CONF` (default 0.7)
   is kept for the next decision even if it fell below the threshold, with a note like
   `"fire downgraded 0.80->0.28"`. A service that fades out otherwise gets a note
   `"medical dropped: evidence faded (…)"`. Notes are de-duplicated and carried forward;
   a service never disappears without an explanation.

### 4. Capture/route state machine (`backend/app/domain/state.py`)

States: `idle → listening → provisional → refined → closed`. Forward-only.

- `idle`: before Help is pressed.
- `listening`: recording started, no chunk analyzed yet.
- `provisional`: first chunk analyzed, first `RouteDecision` emitted (status
  `provisional`).
- `refined`: window closed and final decision emitted (status `refined`).
- `closed`: report handed to dispatch; no more capture updates.

A transition function rejects any backward or skipping move (e.g. `refined → listening`
is illegal). This is a prime PBT target.

**Early finish.** If the capture ends before the last chunk (explicit `end`, or the
caller's connection drops), `finalize` moves `provisional → refined → closed`, marks the
route `refined`, and adds a note ("capture ended early after N of 6 chunks"). A capture
that never received a chunk is left alone. `report.chunks_received` is the next expected
`chunk_index`, which is what makes ordering enforceable.

### 5. Routing fan-out & dispatch (`backend/app/routing/`, `backend/app/dispatch/`)

- On each route decision, the fan-out ensures a queue entry exists for every indicated
  service and updates its payload (transcript, events, location, confidences, status).
- Each `(report, service)` has an independent `DispatchStatus`.
- A rejected `(report, service)` is remembered and never re-added by later route
  updates. An undecided entry is removed if the route stops including its service; a
  confirmed one stays.
- **Triage.** There are four queues: police, fire, medical, and `triage`. A report that
  routes to no service goes to triage instead of being invisible. A responder can
  `assign` it to a service (the entry moves, a note records who sent it, and the
  service's responder must still confirm) or dismiss it. Triage items cannot be
  confirmed (409), and a dismissed or assigned item never returns to triage. If the
  system later classifies the report on its own, the triage entry is removed and the
  service queue(s) get it.
- A WebSocket hub pushes queue changes to connected dashboards.
- Confirm/reject endpoints mutate `DispatchStatus` only; there is deliberately NO
  module that calls any external/real dispatch target. Demo-safety is enforced by
  absence plus an explicit guard constant `REAL_DISPATCH_ENABLED = False`.

### 6. API surface (`backend/app/main.py`)

- `POST /reports` → create a report (returns an unguessable id). Body may name a demo
  `scenario` (demo mode) and a location. An unknown scenario is a 400, out-of-range coordinates a
  422, and a misconfigured `live` backend a 503, all at creation rather than mid-stream.
- `WS /ws/reports/{id}/stream` → caller streams chunks; server streams back route
  decisions as they go provisional → refined. Protocol:
  - client → `{"type":"chunk","chunk_index":N,"transcript":"…","events":[{"kind","confidence"}]}`
    and `{"type":"end"}`. In the default `browser` mode `transcript` / `events` come from
    the device (`null` = unavailable, `""` / `[]` = heard nothing). `audio_b64` is
    accepted (size-limited, validated) for server-side backends but the default caller
    does not send audio. Demo-mode chunks carry no signals;
  - server → `{"type":"route","state","decision"}`, `{"type":"closed","state","decision"}`,
    and `{"type":"error","detail"}`.
  - Chunks must arrive in order, exactly once, while the window is open. Anything else
    (out of order, duplicate, after the final chunk, non-integer index, malformed
    JSON/binary frames, bad base64) gets an `error` reply, leaves the report untouched,
    and keeps the connection open.
  - `end`, or a dropped connection, finalizes the report (see §4) so it never sits in a
    queue marked provisional forever.
- `GET /queues/{queue}` → current snapshot of `police`, `fire`, `medical`, or `triage`.
- `WS /ws/dashboard` → responder subscribes to live queue updates (initial snapshot of
  all four queues, then a full-queue snapshot per change).
- `POST /reports/{id}/{queue}/confirm` and `/reject` → human decision. Rejecting a
  confirmed entry is a 409; confirming a triage item is a 409; deciding on a
  missing/rejected entry is a 404. `reject` on `triage` is "dismiss".
- `POST /reports/{id}/triage/assign?service=…` → send a triage item to a service queue.
- WebSockets live under `/ws` so the dev proxy can forward them without also swallowing
  the `/dashboard` web page.
- **Access control:** if `DASHBOARD_TOKEN` is set, queues, confirm/reject, and the
  dashboard socket require it (`X-Dashboard-Token` header or `?token=`); the socket
  closes with code 1008 on a bad token. Callers never need it. Unset means open, which
  is for local demos only. The `responder` name is a client-supplied label, not an
  identity.

### 7. Frontend

- **Caller** (`src/caller/`): one big Help button and nothing to choose. On press it
  requests the microphone (raw: echo cancellation, noise suppression and auto-gain off,
  because they strip non-speech sounds), then per ~10 s chunk, on the device:
  speech-to-text via the Web Speech API (`lib/speech.ts`, `TranscriptBuffer` splits the
  continuous stream per chunk and survives recognizer restarts) and sound classification
  via vendored YAMNet on TF.js (`lib/sounds.ts`: decode to 16 kHz mono, score, pick the
  scores output by its 521-wide shape, map class names to event kinds, drop weak
  readings). It sends only text and sound labels, shows a "What we heard" panel, and
  explains unavailable capabilities and the privacy trade-off. A fresh `MediaRecorder`
  is used per chunk. Recording starts at the tap; location and report creation run in
  parallel and chunks queue until the socket is open; `end` follows the last chunk. The
  TF.js model loads lazily while the caller reads the page. `?demo=1` shows the scenario
  picker and plays a scripted scenario without the microphone; `?chunkMs=2000` shortens
  chunks. Leaving the page stops everything. Failures are explained: mic denied, mic
  unavailable (insecure origin), connection lost.
- **Dashboard** (`src/dashboard/`): four columns (triage, police, fire, medical), each card
  shows confidences, transcript, events, location, notes, provisional/refined badge, and
  Confirm / Reject buttons (triage cards get Send-to-service and Dismiss instead), repeated
  sound readings collapsed to the strongest per kind, and a note when the device could
  not provide speech or sound. Reconnects with backoff, shows connection state, reports
  failed decisions, and reads an optional `?token=`.
- **Secure context:** browsers expose the microphone only on HTTPS or localhost.
  `npm run dev:phone` serves HTTPS on the LAN (self-signed) for testing on a phone.

## Correctness properties (for property-based testing)

These are the invariants the mock router and state machine must satisfy, tested with
`hypothesis` over generated transcripts/events/priors. (R# references requirements.)

- **P1 — Confidence bounds (R3.1):** for any input, every service confidence in the
  result is within `[0, 1]`.
- **P2 — Confident smoke ⇒ fire (R3.4):** if the input events include a `smoke_alarm`
  at or above `GUARANTEE_MIN_EVENT_CONF`, the result's services include `fire` and
  `fire` is pinned. (A faint alarm does not force it; that is a unit test.)
- **P3 — Determinism (R3.5):** routing the same `(text, events, prior)` twice yields
  equal `RouteDecision`s.
- **P4 — Every routed service is justified (R3.2):** each routed service is at/above
  `MIN_SERVICE_CONF`, pinned, or committed (≥ `HIGH_CONF`) in the prior; routed services
  are always a subset of the three known services.
- **P5 — Monotonic commitment (R4.4):** for any prior and *any generated thresholds*
  (including `MIN_SERVICE_CONF` > `HIGH_CONF`, which forces the "keep despite falling
  below threshold" branch), every service with prior confidence ≥ `HIGH_CONF` is present
  in the next decision.
- **P6 — needs_attention correctness (R3.3):** `needs_attention` is true iff nothing is
  routed.
- **P7 — Forward-only state (R4.6):** over any sequence of requested transitions, a
  transition succeeds iff it moves exactly one step forward, every other request raises,
  and the final rank equals the number of successful steps.
- **P8 — Pinned guarantees persist (R3.4 + R4.2):** fed chunks sequentially with
  arbitrary later text and events, once a confident `smoke_alarm` has been heard every
  later decision still includes `fire`.
- **P9 — Whole-word matching (R3.1):** a keyword buried inside a longer word
  ("begun", "firefly") never routes anything.
- **P10 — Fading (R4.2, R4.9):** with no events and no keyword hits, no unpinned
  service's confidence exceeds its prior value × `CARRY_DECAY`.
- **P11 — Faint alarms don't pin (R4.10):** `smoke_alarm` events below
  `GUARANTEE_MIN_EVENT_CONF` never add to `pinned`. (Found by hand-mutating the router:
  no earlier property caught a faint alarm wrongly pinning `fire`.)

Each property maps to a test file under `backend/tests/property/`. Any counterexample
`hypothesis` shrinks is recorded in `HACKATHON.md` §3.6.

## Error handling

- Analyzer failure on a chunk (R2.5): catch per-signal, record the signal as missing
  in the report, continue. A report with partial signals still routes on what it has.
- Mic denied (R1.3): surfaced as an accessible error; capture does not start.
- Geo denied (R1.4): `Location.known = False`; capture proceeds.
- WebSocket drop: report state persists server-side; dashboard re-subscribes and gets
  a fresh snapshot.

## Testing strategy

- **Unit:** rule-table contributions, decay, negation, thresholds, dispatch hub rules,
  orchestrator ordering/failure/finalize, config loading.
- **Property (`hypothesis`, `fast-check`):** P1–P10 above; client timing helpers.
- **Integration:** full mock flow for every scenario — create report → stream chunks →
  assert provisional then refined decisions → assert queue fan-out → confirm/reject;
  plus hostile input on the stream (out of order, duplicates, late chunks, malformed
  frames, bad audio), reject-stays-rejected, early end, dropped connection, and token
  access control.
- **Manual / not automated:** real microphone capture and geolocation need a browser and
  a device; they are checked by hand (see HACKATHON.md §2).
- **Clean-clone guarantee:** entire suite passes with `ANALYZER_BACKEND=mock` and no
  network/keys (R6.4).
