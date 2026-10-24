# Technology & Conventions

## Stack

### Backend (`backend/`)
- **Language:** Python 3.11+
- **Framework:** FastAPI (HTTP + WebSocket), served with `uvicorn`.
- **Validation / models:** Pydantic v2 for all request/response and domain models.
- **Async:** `async`/`await` throughout the request and streaming paths.
- **Testing:** `pytest` for unit/integration; **`hypothesis`** for property-based
  testing of the routing logic and state machine.
- **Lint/format:** `ruff` (lint) and `ruff format` (format). `mypy` for types.

### Frontend (`frontend/`)
- **Language:** TypeScript (strict mode).
- **Build:** Vite.
- **UI:** React 18.
- **Two apps / routes:**
  - **Caller PWA** (`/`): the one-tap "Help" capture screen.
  - **Dispatch dashboard** (`/dashboard`): the three live queues.
- **Audio capture:** `getUserMedia` with echo cancellation / noise suppression / auto-gain
  OFF (they delete the sounds we want), a fresh `MediaRecorder` per chunk,
  `navigator.geolocation` for location.
- **On-device analysis:** Web Speech API for speech (privacy: in Chrome the browser sends
  audio to Google; this app only receives text) and `@tensorflow/tfjs` + YAMNet for
  sounds (Apache-2.0; loaded lazily). The YAMNet model has three outputs in no promised
  order; find the scores by their 521-wide last dimension.
- **Realtime:** native `WebSocket` to the backend.
- **Testing:** `vitest` + Testing Library for components; **`fast-check`** for PBT on
  client-side pure logic.
- **Checks:** `tsc` in strict mode (`npm run typecheck`). There is no ESLint/Prettier
  setup; do not claim one until it is added.
- **Dependencies:** pin exact versions (backend `requirements.txt`, frontend
  `package.json`) and keep `npm audit` clean.
- **Secure context:** the microphone only works on HTTPS or localhost. Use
  `npm run dev:phone` to test on a phone.

## The Analyzer Seam (most important architectural rule)

All AI/ML work sits behind three interfaces. The rest of the app depends ONLY on
these interfaces, never on a concrete model or vendor SDK:

- `Transcriber.transcribe(chunk) -> Transcript`
- `AudioEventDetector.detect(chunk) -> list[AudioEvent]`
- `Router.route(transcript, events, prior) -> RouteDecision`

Implementations, selected by env var `ANALYZER_BACKEND` (the router is the same rule
table in all of them: `analyzers/rule_router.py`, a real router, not a mock):

- `browser` (DEFAULT): the caller's browser transcribes speech (Web Speech API) and
  classifies sounds (YAMNet on TF.js, vendored in `frontend/public/models/yamnet`) and
  sends text + labels with each chunk. Requires NO API keys and uploads no audio.
- `mock`: deterministic. Plays scripted scenario fixtures. A report created with a
  `scenario` ALWAYS uses it, whatever the configured backend, which is what keeps demos,
  recordings, and property-based tests reproducible.
- `live`: server-side models; the speech and sound adapters are NOT implemented yet (they
  are seams). Intended: calls real models (e.g. a speech-to-text model, an audio-classification
  model, and an LLM for routing) using credentials from `.env`. Selecting `live`
  changes ONLY the source of transcript/events/route; no other code path changes.

Rules:
- Routing, dispatch, queueing, and the WebSocket layer must never import a vendor SDK.
- Adding a new model vendor means adding one new implementation of an interface,
  nothing else.
- The deterministic mock is a first-class, permanently-supported backend, not a stub
  to be deleted later.

## Configuration & Secrets

- All config via environment variables; provide `.env.example` with every key and a
  safe default. `ANALYZER_BACKEND=mock` is the default. The backend reads the repo-root
  `.env` and `backend/.env`; live-backend keys flow through `Settings`, never raw
  `os.environ`. Tests pin `ANALYZER_BACKEND=mock` so a local `.env` cannot change them.
- With `DASHBOARD_TOKEN` unset the API is open (local demo only). Never describe an open
  deployment as secure.
- NEVER commit real secrets. `.env` is gitignored; `.env.example` is committed.
- NEVER add `.kiro` (or any subfolder) to `.gitignore`.

## Testing Approach

- **Unit tests** for pure logic (rule table, confidence math, chunk assembly).
- **Property-based tests (`hypothesis`)** for universal invariants of the router and
  the provisional→refined state machine. Properties are written down in each spec's
  `design.md` and implemented against generated inputs. Target invariants include:
  - confidence for every service is within `[0, 1]`;
  - a confident `smoke_alarm` audio event pins `fire` for the rest of the capture;
  - refinement never silently drops a service previously routed above the high-
    confidence threshold (tested over generated thresholds, not just the defaults);
  - routing is deterministic: same `(transcript, events, prior)` → same decision;
  - keywords match whole words only;
  - the state machine only moves `idle → listening → provisional → refined → closed`
    (no backward jumps).
- A property that cannot fail proves nothing. When writing one, ask what bug it would
  catch and check it actually fails against a deliberately broken implementation.
- The vendored YAMNet is tested on generated audio (Node, CPU backend) through the
  production scoring code. Real microphone hardware, geolocation, and Web Speech accuracy
  are manual checks; say so rather than implying coverage. A synthetic `MediaStream` in
  headless Chrome covers MediaRecorder → decode → classify → WebSocket → dashboard.
- **Integration tests** for the capture → analyze → route → queue → confirm flow
  using the mock backend end to end.
- Run from a clean clone with no keys: `mock` backend must make the full suite pass.

## Coding Conventions

- Domain types are shared vocabulary: `Service` (`police | fire | medical`),
  `AudioEvent`, `Transcript`, `RouteDecision`, `Report`, `DispatchStatus`.
- Keep AI uncertainty explicit: carry confidences, never collapse to a single
  service too early.
- Prefer small pure functions for routing rules so they are trivially PBT-able.
- Every user-facing status string has a stable key for screen-reader and i18n use.
- No `print`-driven control flow; use structured logging.

## Commands (keep these accurate; README mirrors them)

- Backend install: `pip install -r backend/requirements.txt`
- Backend run: `uvicorn app.main:app --reload` (from `backend/`)
- Backend tests: `pytest` (from `backend/`)
- Frontend install: `npm install` (from `frontend/`)
- Frontend dev: `npm run dev` (from `frontend/`), or `npm run dev:phone` for HTTPS on
  the LAN
- Frontend checks: `npm run typecheck`, `npm run test`, `npm run build` (from `frontend/`)
- Backend lint/types: `ruff check app tests` and `mypy app` (from `backend/`)
