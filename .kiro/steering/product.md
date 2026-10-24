# Product Overview

**Project:** Help Router
**Hackathon:** Hackachusetts 2026
**Track:** Civic Services / Civic Action

## Purpose

In an emergency, a person under stress often does not know which number to call,
cannot talk for long, and may not be able to say where they are. The first minute
holds the most evidence, and it is usually lost.

Help Router turns one spoken word into a routed emergency report. A person says
"Help"; the phone records the next 60 seconds of audio together with location; the
system works out which service is needed (police, fire, medical, or several) and
delivers the details to that service's live dispatch queue, where a human responder
confirms every dispatch.

## Users

- **Caller:** a person in an emergency using the phone web app. May be injured,
  panicked, non-technical, or unable to speak clearly. The interface must work with
  a single action and must never block on the caller doing anything else.
- **Responder / dispatcher:** a trained human watching a service dashboard (police,
  fire, or medical). They triage incoming reports and confirm or reject each
  dispatch. They are the human in the loop; the system never dispatches on its own.

## Key Features

- **One-tap capture.** A single "Help" button records 60 seconds of audio in short
  chunks and captures geolocation, with no further input required from the caller.
- **Voice trigger (opt-in).** Once enabled (remembered per device), saying "Help" starts
  the same capture hands-free (`listenForWakeWord` in `frontend/src/lib/speech.ts`). The
  button always remains for callers who cannot speak.
- **Multi-signal understanding.** The caller's device transcribes speech and
  classifies sounds (screams, breaking glass, sirens, smoke alarms, explosions); a
  router fuses transcript + events into a set of services, each with a confidence
  score. Today the router is a transparent rule table; an LLM router is the `live` seam.
- **Provisional then refined routing.** A route is produced provisionally after
  about 10 seconds and refined as more audio arrives over the full 60 seconds.
- **Dispatch dashboard.** Police, fire, and medical queues update live, plus a
  **triage** queue for reports the system could not classify. A report can appear in
  more than one service queue when multiple services are needed.
- **Human-confirmed dispatch.** Every dispatch is confirmed by a responder. Nothing
  is auto-dispatched.

## Domain Rules (always apply)

- **Demo safety:** the system NEVER contacts real emergency services (no 911, no PSAP,
  no real dispatch API). All routing targets our own dashboard queues. This must be
  stated in the UI and enforced in code.
- **Human in the loop:** the system proposes; a responder disposes. No automatic
  dispatch, ever.
- **Services are a set, not a single choice:** police, fire, and medical are
  independent. Zero, one, or several may apply to a single report.
- **Confidence is always in [0, 1].**
- **Refinement is monotonic in commitment:** refining a route with more audio must
  not silently drop a service that was already routed with high confidence; it may
  add services, raise/lower confidences, or flag a downgrade for the responder, but
  a confidently-routed service is never quietly removed. Any service that fades out
  leaves a note saying so.
- **An unclassifiable report is never invisible:** it goes to the triage queue for a
  human, and the caller is not told more than is true.
- **Pressing Help requires no choices.** Scripted scenarios exist only in an explicit
  demo mode (`?demo=1`) and for tests.
- **Device-supplied signals are claims, not facts.** They are unauthenticated and speech
  recognition can hallucinate words; the human-confirmed dispatch is the control.
- **Missed emergencies cost more than false alarms:** heuristics (like negation
  handling) stay narrow, and a human reviews every dispatch.
- **A rejected report stays rejected** for that service; later updates do not bring it
  back.
- **Provisional results are labeled provisional** until the capture window closes or
  the route stabilizes.

## Accessibility & Equity Goals

- Operable by one tap; no reading required to trigger help.
- Large touch target, high contrast, screen-reader labels on all controls.
- Clear, honest status at every step ("Listening…", "Provisional route", "Sent to
  dispatch") so a stressed user is never guessing.
- Works offline-of-paid-APIs by default (deterministic mock backend) so the tool is
  free to test and does not depend on a caller's or a tester's API budget.
- Does not require the caller to know jurisdiction, phone numbers, or service names.

## What a Successful Outcome Looks Like

- A tester can clone the repo, run it with no API keys, press "Help" and speak or play a
  sound, and watch a report flow through provisional → refined routing into the correct
  dashboard queue(s), then confirm a dispatch. The scripted demo mode makes the same
  flow reproducible without a microphone.
- The routing logic is covered by property-based tests over its invariants.
- Every Kiro claim in `HACKATHON.md` points to a real file or workflow in the repo.
