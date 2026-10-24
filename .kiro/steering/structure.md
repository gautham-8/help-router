# Repository Structure & Naming

## Top-level layout

```
help-router/
├── .kiro/
│   ├── specs/                      # One folder per feature (spec-driven dev)
│   │   └── <feature-name>/
│   │       ├── requirements.md     # EARS-style user stories + acceptance criteria
│   │       ├── design.md           # Architecture, data models, interfaces, PBT properties
│   │       └── tasks.md            # Discrete, trackable implementation tasks
│   ├── steering/
│   │   ├── product.md              # Product purpose, users, domain rules, a11y goals
│   │   ├── tech.md                 # Stack, the analyzer seam, testing approach
│   │   └── structure.md            # This file
│   ├── hooks/                      # Event-triggered agent automations
│   └── settings/
│       └── mcp.json                # MCP server config (no secrets; env vars only)
├── backend/                        # FastAPI service
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routes, WebSocket endpoints
│   │   ├── domain/                 # Pure domain models & types (Pydantic)
│   │   │   ├── models.py           # Service, AudioEvent, Transcript, RouteDecision, Report
│   │   │   └── state.py            # Capture/route state machine
│   │   ├── analyzers/              # THE SEAM
│   │   │   ├── interfaces.py       # Transcriber, AudioEventDetector, Router protocols
│   │   │   ├── rule_router.py      # The router: a transparent rule table (all backends)
│   │   │   ├── browser/            # DEFAULT: signals the caller's device attached
│   │   │   ├── mock/               # Scripted scenarios (demo mode, tests)
│   │   │   │   ├── transcriber.py
│   │   │   │   ├── detector.py
│   │   │   │   └── scenarios/       # Scripted emergency fixtures (JSON)
│   │   │   ├── live/                # Real-model backend (behind .env)
│   │   │   └── factory.py           # Selects backend from ANALYZER_BACKEND
│   │   ├── routing/                # Fan-out to service queues
│   │   ├── dispatch/               # Queues + human-confirm workflow
│   │   └── config.py               # Env-driven settings
│   ├── tests/
│   │   ├── unit/
│   │   ├── property/               # hypothesis PBT
│   │   └── integration/
│   ├── requirements.txt
│   └── pyproject.toml              # ruff/mypy/pytest config
├── frontend/                       # Vite + React + TS
│   ├── src/
│   │   ├── caller/                 # One-tap Help page (/)
│   │   ├── dashboard/              # Three-queue dispatch UI (/dashboard)
│   │   ├── lib/                    # api/ws client, capture, speech, sounds (YAMNet), timing, types
│   ├── public/models/yamnet/       # Vendored YAMNet (TF.js) + class map; committed on purpose
│   │   └── main.tsx
│   ├── tests/
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── .env.example                    # Every env key with safe defaults (mock backend)
├── .gitignore                      # MUST NOT list .kiro
├── HACKATHON.md                    # Submission compliance + Kiro write-up
├── GUIDELINES.md                   # Submission brief (source of truth for compliance)
└── README.md                       # Summary, track, setup/run/test, demo link
```

## Naming conventions

- **Spec folders:** kebab-case feature names, e.g. `help-capture-and-routing`.
- **Python:** `snake_case` for modules/functions, `PascalCase` for classes, type
  aliases in `PascalCase` (`Service`, `RouteDecision`).
- **TypeScript:** `camelCase` for values/functions, `PascalCase` for components and
  types, one component per file named after the component.
- **Scenario fixtures:** `backend/app/analyzers/mock/scenarios/<kebab-name>.json`
  (e.g. `kitchen-fire.json`, `break-in.json`, `car-crash-injuries.json`,
  `multi-service.json`). Each fixture scripts the per-chunk transcript and events
  across the 60-second window.
- **Tests:** mirror the source path; `test_<unit>.py` / `<unit>.test.ts(x)`. Integration
  fixtures that reset state live in `tests/integration/conftest.py` (not the top-level
  conftest: Hypothesis rejects function-scoped fixtures on `@given` tests).
- **WebSocket routes** live under `/ws/...` so a dev proxy never shadows a page route.
- **Status keys:** `SCREAMING_SNAKE_CASE` stable identifiers for UI status strings.

## Where things go (quick rules)

- New domain concept → `backend/app/domain/models.py` (and shared TS type in
  `frontend/src/lib/`).
- New AI capability → a new implementation under `analyzers/mock/` and
  `analyzers/live/`, wired in `analyzers/factory.py`. Never inside routing/dispatch.
- New demo scenario → a JSON fixture in `analyzers/mock/scenarios/`, plus a dropdown
  entry in the caller UI.
- New invariant to protect → a property test in `backend/tests/property/` and a note
  in the owning spec's `design.md`.
