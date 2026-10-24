# Tasks: Help Capture and Routing

Execute top to bottom. Each task notes the requirements it satisfies. Check off as
completed and keep `HACKATHON.md` §3.8 updated as tasks land.

- [x] 1. Scaffold backend project
  - Create `backend/` with `app/` package, `requirements.txt` (fastapi, uvicorn,
    pydantic, pytest, hypothesis, ruff, mypy), and `pyproject.toml` (ruff/mypy/pytest
    config).
  - Add `app/config.py` reading `ANALYZER_BACKEND` (default was `mock`; now `browser`, see task 24) and thresholds
    (`MIN_SERVICE_CONF=0.3`, `HIGH_CONF=0.7`).
  - _Requirements: 2.3, 6.1_

- [x] 2. Define domain models
  - Implement `app/domain/models.py`: `Service`, `AudioEvent`, `Transcript`,
    `RouteDecision`, `Location`, `Report`, `DispatchStatus`, `CaptureState`.
  - _Requirements: 3.1, 3.2, 5.7_

- [x] 3. Implement the capture/route state machine
  - `app/domain/state.py`: forward-only transitions
    `idle→listening→provisional→refined→closed`; reject backward/skip moves.
  - _Requirements: 4.6_

- [x] 4. Define analyzer interfaces and factory
  - `app/analyzers/interfaces.py`: `Transcriber`, `AudioEventDetector`, `Router`
    protocols and `AudioChunk` type.
  - `app/analyzers/factory.py`: select backend from `ANALYZER_BACKEND`.
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 5. Build the deterministic mock backend
  - `analyzers/mock/transcriber.py`, `detector.py`: return scripted output by
    `(scenario, chunk_index)`.
  - `analyzers/mock/router.py`: pure rule-table router per design §3 (clamping,
    thresholds, smoke⇒fire guarantee, monotonic commitment, carry-forward).
  - _Requirements: 2.4, 3.1–3.5, 4.4_

- [x] 6. Author demo scenario fixtures
  - `analyzers/mock/scenarios/`: `kitchen-fire.json`, `break-in.json`,
    `car-crash-injuries.json`, `multi-service.json`, each scripting chunks 0..5.
  - _Requirements: 6.2, 6.3_

- [x] 7. Routing fan-out and dispatch queues
  - `app/routing/`: turn a `RouteDecision` into/within per-service queue entries.
  - `app/dispatch/`: three queues, independent `DispatchStatus` per (report, service),
    confirm/reject, and the `REAL_DISPATCH_ENABLED = False` demo-safety guard.
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6_

- [x] 8. FastAPI endpoints and WebSocket hub
  - `app/main.py`: `POST /reports`, `WS /reports/{id}/stream` (chunks in, decisions
    out, provisional→refined), `GET /queues/{service}`, `WS /dashboard`,
    confirm/reject routes. Per-chunk analyzer-failure handling.
  - _Requirements: 1.2, 2.5, 4.1–4.3, 4.5, 5.3, 5.7_

- [x] 9. Property-based tests (`hypothesis`)
  - `backend/tests/property/`: P1 bounds, P2 smoke⇒fire, P3 determinism, P4 set
    routing, P5 monotonic commitment, P6 needs_attention, P7 forward-only state,
    P8 carry-forward guarantee. Map each to design §properties.
  - Record any shrunk counterexamples in `HACKATHON.md` §3.6.
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 4.4, 4.6_

- [x] 10. Unit and integration tests (mock backend)
  - Unit: rule contributions, clamping, thresholds, chunk assembly.
  - Integration: create report → stream a scenario → assert provisional then refined
    → assert fan-out → confirm/reject. No network/keys.
  - _Requirements: 6.1, 6.4_

- [x] 11. Scaffold frontend project
  - `frontend/` with Vite + React + TS (strict), ESLint/Prettier, `vitest`.
  - Shared types in `src/lib/` mirroring domain models; WebSocket client.
  - _Requirements: 1.1_

- [x] 12. Caller PWA
  - `src/caller/`: accessible one-tap Help button (large target, ARIA labels),
    mic+geo capture via `MediaRecorder`/`geolocation`, 60 s / ~10 s chunking, demo
    scenario picker, live status (`LISTENING`/`PROVISIONAL_ROUTE`/`SENT_TO_DISPATCH`),
    permission-denied messaging, persistent demo-safety banner.
  - _Requirements: 1.1–1.6, 6.2_

- [x] 13. Dispatch dashboard
  - `src/dashboard/`: three live queues over WebSocket; cards showing confidences,
    transcript, events, location, provisional/refined badge; Confirm/Reject controls.
  - _Requirements: 4.5, 5.1–5.3, 5.7_

- [x] 14. Live backend adapters (optional, behind `.env`)
  - `analyzers/live/`: real speech-to-text, audio-event, and LLM router adapters
    implementing the same interfaces. No downstream changes.
  - _Requirements: 2.1, 2.2 (live path)_

- [x] 15. Wiring, docs, and compliance pass
  - `.env.example` with all keys (default `ANALYZER_BACKEND=mock`); confirm `.env`
    gitignored and `.kiro` NOT gitignored.
  - Update README (summary, track, setup/run/test, demo link, link to HACKATHON.md).
  - Update `HACKATHON.md` §3.2/§3.6/§3.8 with spec evidence and PBT results.
  - _Requirements: 6.1, 6.4_

## Review pass (after the first full implementation)

A code review of tasks 1-15 found bugs the original tests did not cover. Each fix below
has a test that fails without it.

- [x] 16. Fix the dashboard page and WebSocket routing
  - Move WebSockets under `/ws` (`/ws/dashboard`, `/ws/reports/{id}/stream`) so the dev
    proxy no longer swallows the `/dashboard` page.
  - _Requirements: 6.6_

- [x] 17. Make capture real and complete
  - Record real audio in standalone per-chunk blobs, send it base64 over the socket,
    queue chunks until the socket is open, send `end` only after the last chunk, release
    the mic and close the socket on unmount, and explain mic-denied / mic-unavailable /
    connection-lost states. Add `npm run dev:phone` (HTTPS) for on-device testing.
  - _Requirements: 1.1-1.3, 4.8, 6.6_

- [x] 18. Harden the capture stream
  - Enforce chunk ordering and the open window, validate indexes, frames, and audio,
    finalize on `end` and on disconnect, and reject unknown scenarios and bad
    coordinates at report creation.
  - _Requirements: 4.7, 4.8, 6.5_

- [x] 19. Fix dispatch semantics
  - Rejected reports stay rejected; confirmed ones cannot be rejected.
  - _Requirements: 5.5_

- [x] 20. Fix routing quality
  - Whole-word keyword matching, narrow clause-aware negation, confidence decay with
    explanatory notes, pinned guarantees, and a minimum confidence for the smoke-alarm
    guarantee. Rework P2/P4/P5/P7/P8 so they assert real behavior, add P9/P10.
  - _Requirements: 3.1, 3.4, 4.4, 4.9, 4.10_

- [x] 21. Configuration and access control
  - Read the repo-root `.env`, pass live-backend keys through settings, pin the test
    environment to the mock backend, add optional `DASHBOARD_TOKEN`, restrict CORS, and
    bound reports and audio size.
  - _Requirements: 6.4, 6.6, 7.1-7.4_

- [x] 22. Tooling
  - Backend tests-on-save hook uses the project venv. Upgrade vite/vitest (0 `npm audit`
    findings), pin all frontend versions, drop the `lint` script that referenced an
    uninstalled ESLint, and add component and timing tests.

## Real analysis (replacing the scenario picker)

The first implementation could only route a scenario the user picked; nothing analyzed the
caller's voice or sounds. These tasks make Help work from what the device hears.

- [x] 23. Rename the router
  - `MockRouter` becomes `RuleRouter` (`analyzers/rule_router.py`): it is the real router
    for every backend, not a mock.
  - _Requirements: 3_

- [x] 24. Add the `browser` analyzer backend and make it the default
  - `ClientTranscriber` / `ClientAudioEventDetector`, `SignalMissing`, validated
    `ChunkSignals`, scenario reports always use the scripted analyzers.
  - _Requirements: 2.3-2.7, 6.1_

- [x] 25. On-device sound classification
  - Vendor YAMNet (TF.js graph model, Apache-2.0) in `frontend/public/models/yamnet/`.
    Decode to 16 kHz mono, score, pick the scores output by its 521-wide shape (not by
    position), map classes to event kinds by display name, drop weak detections. Capture
    raw audio (no echo cancellation / noise suppression / AGC).
  - _Requirements: 8.2-8.4_

- [x] 26. On-device speech recognition
  - Web Speech API wrapper with auto-restart, plus `TranscriptBuffer` for per-chunk text
    without losing or repeating words.
  - _Requirements: 8.2, 8.5_

- [x] 27. Caller UI without the picker
  - Help works with no choices; "What we heard" panel; capability and privacy notes;
    scenario picker only under `?demo=1` (which does not use the microphone).
  - _Requirements: 8.1, 8.5-8.7, 6.1-6.2_

- [x] 28. Triage queue
  - Found while testing in a real browser: an unclassifiable report was flagged but shown
    to no responder, while the caller saw "Sent to dispatch". Add a triage queue with
    send-to-service and dismiss actions, and 409 for confirming a triage item.
  - _Requirements: 3.3, 5.8, 5.9_

- [x] 29. Verification
  - Real YAMNet on generated audio in vitest; real headless Chrome with a synthetic
    microphone through the whole pipeline; mutation checks; dev-server runs.
