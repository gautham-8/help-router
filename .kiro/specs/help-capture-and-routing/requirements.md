# Requirements: Help Capture and Routing

## Introduction

This spec covers the core Help Router flow: a caller triggers capture with one tap,
the phone records 60 seconds of audio in chunks with location, three analyzers turn
that audio into a set of needed services with confidences, the route is produced
provisionally and then refined, and the report is placed into the matching dispatch
queue(s) where a human responder confirms every dispatch. The demo never contacts
real emergency services.

Requirements use EARS-style acceptance criteria (WHEN … THE SYSTEM SHALL …).

## Glossary

- **Service:** one of `police`, `fire`, `medical`.
- **Audio chunk:** a short slice of recorded audio (≈10 s) streamed during capture.
- **Audio event:** a detected non-speech sound (e.g. `scream`, `glass_breaking`,
  `siren`, `smoke_alarm`) with a confidence in `[0, 1]`.
- **Route decision:** a mapping from service → confidence in `[0, 1]`, plus a status
  of `provisional` or `refined`.
- **Report:** a capture session with its transcript, events, route decision, and
  location.
- **Dispatch:** the act of a responder confirming a report in their queue.
- **High-confidence threshold:** the confidence at/above which a service is treated
  as committed for the monotonicity rule (configurable; default 0.7).

---

## Requirement 1: One-tap capture

**User story:** As a caller in an emergency, I want to press one button and have the
phone start recording and locating me, so that I get help without having to explain
anything or know who to call.

#### Acceptance Criteria
1. WHEN the caller taps the Help control THE SYSTEM SHALL begin audio recording and
   request the device location without requiring any further input.
2. WHEN recording begins THE SYSTEM SHALL continue for 60 seconds and emit the audio
   as sequential chunks of approximately 10 seconds.
3. WHEN the microphone permission is denied THE SYSTEM SHALL display a clear,
   screen-reader-announced message explaining that audio is required and SHALL NOT
   silently fail.
4. WHEN location permission is denied or unavailable THE SYSTEM SHALL still proceed
   with audio capture and SHALL mark the report location as unknown.
5. WHILE recording is in progress THE SYSTEM SHALL display an accessible status
   indicating that it is listening and how much time remains.
6. WHEN the caller taps the Help control THE SYSTEM SHALL present a visible,
   persistent notice that this is a demo and no real emergency service is contacted.

## Requirement 2: Multi-signal analysis

**User story:** As the system, I want to understand both what is said and what is
heard, so that I can route correctly even when the caller cannot speak clearly.

#### Acceptance Criteria
1. WHEN an audio chunk arrives THE SYSTEM SHALL transcribe it to text via the
   configured `Transcriber`.
2. WHEN an audio chunk arrives THE SYSTEM SHALL detect audio events via the
   configured `AudioEventDetector`, each with a confidence in `[0, 1]`.
3. WHEN analysis runs THE SYSTEM SHALL use the backend named by `ANALYZER_BACKEND`
   (`browser`, `mock`, or `live`), defaulting to `browser` when the variable is unset.
4. WHEN a report names a demo scenario THE SYSTEM SHALL use the scripted `mock`
   analyzers whatever the configured backend, and SHALL produce the same outputs for the
   same scenario and chunk index (deterministic).
5. WHEN `ANALYZER_BACKEND=browser` THE SYSTEM SHALL take each chunk's transcript and
   sound events from the caller's device, SHALL require no API keys, and SHALL NOT
   require a scenario to be chosen. A signal the device could not produce SHALL be
   recorded as missing, which is distinct from "heard nothing".
6. THE SYSTEM SHALL validate device-supplied signals (transcript length, number of
   events, known event kinds, confidences in `[0, 1]`) and SHALL reject an invalid
   payload without counting the chunk. Device-supplied signals are unauthenticated and
   SHALL be treated as claims for a human to verify.
7. IF an analyzer fails for a chunk THE SYSTEM SHALL continue with the remaining
   signals and SHALL record that the signal was missing rather than aborting capture.

## Requirement 8: On-device speech and sound analysis

**User story:** As a caller, I want to press Help and have the app work out what is
happening from what it hears, so that I do not have to choose or describe anything.

#### Acceptance Criteria
1. WHEN the caller presses Help THE SYSTEM SHALL NOT ask them to choose a scenario or
   service; the demo scenario picker SHALL be available only in an explicit demo mode.
2. WHEN a chunk of audio is recorded THE SYSTEM SHALL, on the caller's device,
   transcribe speech (where the browser supports it) and classify sounds (screams,
   breaking glass, sirens, smoke alarms, explosions, generic alarms), and send only the
   resulting text and sound labels with their confidences.
3. THE SYSTEM SHALL capture audio without echo cancellation, noise suppression, or
   automatic gain control, because those filters remove non-speech sounds.
4. THE SYSTEM SHALL bundle the sound-classification model with the repository so it
   works offline and from a clean clone.
5. IF speech recognition or sound classification is unavailable THE SYSTEM SHALL say so
   to the caller, continue with the other signal, and mark the missing signal in the
   report.
6. THE SYSTEM SHALL show the caller what it heard for each chunk, and SHALL tell the
   caller, before they press Help, that the browser may send speech to its vendor's
   recognition service and that this app receives only text and sound labels.
7. IF the page is not on a secure origin THE SYSTEM SHALL explain that the microphone
   needs HTTPS or localhost.

## Requirement 3: Service routing with confidence

**User story:** As the system, I want to combine transcript and events into a set of
services with confidence, so that one or several of police, fire, and medical can be
alerted as appropriate.

#### Acceptance Criteria
1. WHEN transcript and events are available for a report THE SYSTEM SHALL produce a
   route decision mapping each applicable service to a confidence in `[0, 1]`.
2. WHEN more than one service is indicated THE SYSTEM SHALL include all indicated
   services in the route decision (routing is a set, not a single choice).
3. WHEN no service is clearly indicated THE SYSTEM SHALL produce an empty route,
   SHALL flag it for responder attention rather than guessing a single service, and
   SHALL place the report in a **triage** queue visible to responders (see
   Requirement 5), so that an unclassifiable emergency is never invisible.
4. WHEN a `smoke_alarm` audio event is present THE SYSTEM SHALL include `fire` among
   the routed services.
5. WHEN the same `(transcript, events, prior route)` input is routed twice THE
   SYSTEM SHALL return the same decision (deterministic routing).

## Requirement 4: Provisional then refined routing

**User story:** As a responder, I want an early provisional route that sharpens as
more audio arrives, so that I can start triaging within seconds without being misled.

#### Acceptance Criteria
1. WHEN approximately 10 seconds of audio (the first chunk) has been analyzed THE
   SYSTEM SHALL emit a route decision with status `provisional`.
2. WHILE further chunks arrive THE SYSTEM SHALL update the route decision, carrying
   the prior decision as input to the next routing step.
3. WHEN the 60-second window closes THE SYSTEM SHALL emit a final route decision with
   status `refined`.
4. WHEN refining a route THE SYSTEM SHALL NOT silently remove a service whose
   confidence in the prior decision was at or above the high-confidence threshold;
   it MAY lower the confidence or mark a downgrade, but the service SHALL remain
   visible to the responder with its change indicated.
5. THE SYSTEM SHALL label every pre-final decision as provisional in the responder UI.
6. THE SYSTEM SHALL only transition capture/route state forward through
   `idle → listening → provisional → refined → closed` and SHALL NOT move backward.
7. WHEN audio chunks arrive THE SYSTEM SHALL accept each chunk index exactly once and in
   order while the window is open, and SHALL reject (with an error reply, leaving the
   report unchanged and the connection open) any chunk that is out of order, duplicated,
   late, malformed, or carries invalid audio.
8. WHEN the caller ends the capture early, or the caller's connection drops, THE SYSTEM
   SHALL finalize the report (route status `refined`, state `closed`) and note that the
   capture ended early, so no report stays provisional indefinitely.
9. WHILE a service receives no fresh evidence THE SYSTEM SHALL let its confidence fade
   rather than hold its peak, and SHALL record a note whenever a previously routed
   service is dropped or downgraded.
10. WHEN a hard-guarantee audio event (a `smoke_alarm` at or above the configured
    minimum confidence) is heard THE SYSTEM SHALL keep the guaranteed service routed for
    the rest of the capture; a fainter event SHALL NOT force it.

## Requirement 5: Dispatch dashboard (three service queues plus triage) with human confirmation

**User story:** As a responder, I want incoming reports to appear live in my
service's queue so I can confirm or reject each dispatch, and I want reports the
system could not classify to reach a human instead of disappearing.

#### Acceptance Criteria
1. WHEN a route decision includes a service THE SYSTEM SHALL place the report into
   that service's queue (police, fire, or medical).
2. WHEN a report routes to multiple services THE SYSTEM SHALL place it into each
   corresponding queue, and each queue SHALL manage its own confirmation state.
3. WHEN a report's queue entry is created or updated THE SYSTEM SHALL push the change
   to connected dashboards in real time.
4. WHEN a responder confirms a report THE SYSTEM SHALL record the dispatch as
   confirmed, including who/when, and SHALL NOT dispatch before this confirmation.
5. WHEN a responder rejects a report THE SYSTEM SHALL record the rejection and remove
   it from the active queue, and SHALL NOT re-add it to that queue when later route
   updates for the same report arrive. A confirmed dispatch SHALL NOT be rejectable.
6. THE SYSTEM SHALL NEVER contact a real emergency service; all dispatch targets are
   internal demo queues, and this SHALL be enforced in code (no real dispatch
   integration exists in the codebase).
7. WHEN a report shows transcript, events, location, and confidences THE SYSTEM SHALL
   present them to the responder so the human decision is informed, including which
   signals the caller's device could not provide.
8. WHEN a report routes to no service THE SYSTEM SHALL place it in the triage queue.
   A responder SHALL be able to send it to police, fire, or medical, or dismiss it.
   Sending it on SHALL NOT count as a dispatch (the service's responder must still
   confirm), a triage item SHALL NOT be confirmable, and a dismissed or sent-on item
   SHALL NOT return to triage.
9. WHEN the system later classifies a report that is in triage THE SYSTEM SHALL move it
   to the matching service queue(s) and remove it from triage.

## Requirement 6: Reproducible, key-free demo

**User story:** As a judge or tester, I want to run the whole thing from a clean
clone without any API keys and see a realistic emergency play out the same way every
time.

#### Acceptance Criteria
1. WHEN the project is cloned fresh and run with default configuration THE SYSTEM
   SHALL operate end-to-end using the `browser` backend without any API keys, and
   SHALL also offer an explicit demo mode (`?demo=1`) that plays a scripted scenario
   without using the microphone.
2. WHEN the caller selects a demo scenario in demo mode THE SYSTEM SHALL play that
   scenario's scripted transcript and events across the 60-second window.
3. THE SYSTEM SHALL ship at least the scenarios: kitchen fire (→ fire), break-in
   (→ police), car crash with injuries (→ police + medical), and a multi-service
   situation (→ police + fire + medical).
4. WHEN the test suite runs with the default backend THE SYSTEM SHALL pass without
   network access or credentials, even if the developer has a local `.env`.
5. WHEN a report is created with an unknown demo scenario, or a misconfigured `live`
   backend is selected, THE SYSTEM SHALL fail at creation with a clear error rather than
   silently producing empty results mid-stream.
6. WHEN the user follows the README, THE SYSTEM SHALL read configuration from the
   repo-root `.env`, serve both the caller page (`/`) and the dashboard page
   (`/dashboard`) in development, and be usable from a phone over HTTPS.

## Requirement 7: Access control and data handling

**User story:** As an operator, I want to keep caller data and dispatch decisions away
from anyone who should not see them, so that a shared demo URL does not expose
locations or let strangers confirm dispatches.

#### Acceptance Criteria
1. WHERE `DASHBOARD_TOKEN` is set THE SYSTEM SHALL require it for reading queues,
   confirming or rejecting dispatches, and subscribing to the dashboard stream, and
   SHALL close the stream with a policy-violation code on a bad token. Callers SHALL
   NOT need it.
2. THE SYSTEM SHALL generate unguessable report identifiers and restrict browser
   origins to a configured list.
3. THE SYSTEM SHALL bound its in-memory report store and the size of any single audio
   chunk.
4. THE SYSTEM SHALL document that with no token set the API is open and suitable only
   for local demos, and that the responder name is a label, not an identity.
