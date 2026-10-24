# Help Router

**Hackachusetts 2026 — Track: Civic Services / Civic Action**

Turn one spoken word into a routed emergency report. A person says "Help"; their
phone records the next 60 seconds of audio with location; the system works out which
service is needed (police, fire, medical, or several) and delivers the details to that
service's live dispatch queue, where a human responder confirms every dispatch.

> **Demo safety:** This project never contacts real emergency services. Every route
> targets our own dashboard queues, and a human confirms each dispatch.

**Live demo:** [help-router-frontend.onrender.com](https://help-router-frontend.onrender.com/) (caller page; responder board at `/dashboard`)
**Submission & Kiro write-up:** see [HACKATHON.md](./HACKATHON.md)

## Overview

In an emergency a person under stress often does not know which number to call, cannot
talk for long, and may not be able to say where they are. The first minute holds the
evidence, and it is usually lost. Help Router captures that minute and routes it.

- **One-tap capture** — press Help and nothing else: no scenario, no service to pick. The
  phone listens in ~10 s chunks for a minute and shares your location.
- **Hands-free voice trigger (opt-in)** — turn it on once and just say "Help" to start the
  same capture; the words said with it go into the first chunk. The choice is remembered.
- **Multi-signal understanding, on the device** — the browser turns speech into text
  (Web Speech API) and classifies sounds (Google's YAMNet via TensorFlow.js: screams,
  breaking glass, sirens, smoke alarms, explosions). Only text and sound labels are sent.
- **Rule-based routing with confidences** — a transparent rule table fuses words and
  sounds into a set of services, each with a confidence. (A meaning-aware LLM router is a
  planned future direction, not part of this build.)
- **Provisional then refined** — a route appears after ~10 s and sharpens over the minute.
- **Dispatch dashboard** — police / fire / medical queues plus a **triage** queue for
  anything the system could not classify, so an unclear emergency still reaches a human.
  Every dispatch is human-confirmed. One report can appear in several queues.

### What is real and what is not
| Part | Status |
|---|---|
| Speech → text | Real, but done by the **caller's browser** speech service. In Chrome that means audio goes to Google; Safari uses Apple. This app receives only the text. Not available in every browser (e.g. Firefox). With the voice trigger on, that speech service hears the room the whole time the page is open. |
| Sound detection | Real. YAMNet runs on the device; the model is in this repo (`frontend/public/models/yamnet`, 15 MB), so it works offline. |
| Routing | A hand-written rule table (keywords + sounds), not a trained model or an LLM. |
| Demo mode (`/?demo=1`) | Plays a scripted scenario and does not use the microphone. For recordings and offline demos. |

Limits worth knowing: browser speech recognition can **mishear or invent words** (even
from noise), a sound classifier can be wrong, and the rules are simple. That is why a
human confirms every dispatch, and why anything unclear goes to triage.

## Getting Started

### Prerequisites
- Python 3.11+
- Node 22.12+ (the Vite 8 / Vitest 5 toolchain requires it)
- No API keys required

### Installation
```bash
git clone https://github.com/gautham-8/help-router.git
cd help-router

# Config (optional; the defaults already work). Read from the repo root.
cp .env.example .env

# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ..

# Frontend
cd frontend && npm install && cd ..
```

### Run
Use two terminals.
```bash
# Terminal 1 — backend (from backend/)
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (from frontend/)
npm run dev
```
- Caller: <http://localhost:5173/> — allow the microphone, press **Help**, then speak (try
  "there is a fire in my kitchen") or play a sound. Use Chrome or Safari for speech. Or tap
  **Turn on voice trigger** and say "Help, there is a fire in my kitchen".
- Responder: <http://localhost:5173/dashboard> — open it first; watch the report arrive,
  then confirm, reject, or (in the Triage column) send it to a service.
- Add `?chunkMs=2000` to the caller URL for a 12-second run instead of 60 seconds.
- No microphone, or want a repeatable run? Open <http://localhost:5173/?demo=1&chunkMs=2000>,
  pick a scripted scenario, and press Help.

### Try it on a phone
Browsers only allow the microphone on HTTPS (or localhost), so a phone opening
`http://<laptop-ip>:5173` cannot record. Use the HTTPS dev mode instead:
```bash
# from frontend/
npm run dev:phone
```
Open `https://<laptop-ip>:5173` on the phone (same Wi-Fi) and accept the one-time
self-signed-certificate warning. The sound model downloads on first load (about 15 MB over
your Wi-Fi). Physical microphone hardware, location, and speech accuracy are checked by
hand on a device; the automated tests cover everything after the microphone.

### Testing and checks
```bash
# Backend (from backend/): unit + property-based + integration
.venv/bin/python -m pytest
.venv/bin/ruff check app tests
.venv/bin/mypy app

# Frontend (from frontend/)
npm run typecheck
npm run test
npm run build
```
The whole suite runs with no network or credentials, even if you have a local `.env`. It
includes running the real YAMNet model on generated audio.

## Security notes
- With `DASHBOARD_TOKEN` unset, the API is **open**: anyone who can reach it can read
  every report (including locations) and confirm or reject dispatches. That is fine for
  a local demo and **not** for a public URL.
- To protect it, set `DASHBOARD_TOKEN=<secret>` in `.env` and open the dashboard as
  `/dashboard?token=<secret>`. Callers never need the token.
- The responder name shown on a confirmed dispatch is a label the browser supplies, not a
  verified identity.
- Sounds and words come from the caller's device and are **unauthenticated claims**: a
  hostile client could send a fake "smoke alarm". Human confirmation is the control.
- Reports live in memory only and are lost on restart (capped at 500).

## Project Structure
```
help-router/
├── .kiro/
│   ├── specs/help-capture-and-routing/   # requirements.md, design.md, tasks.md
│   ├── steering/                         # product.md, tech.md, structure.md
│   ├── hooks/                            # guard-kiro-tracked, backend-tests-on-save
│   └── settings/                         # cli.json (Kiro IDE settings)
├── backend/                              # FastAPI + analyzer seam + tests
├── frontend/                             # Vite + React caller page and dashboard
├── .env.example
├── HACKATHON.md                          # submission compliance + Kiro write-up
└── README.md
```

> Build status: backend and frontend are implemented and tested (see HACKATHON.md §2
> for current results). Task tracking lives in
> `.kiro/specs/help-capture-and-routing/tasks.md`.

## Contributing
Work through tasks in `.kiro/specs/help-capture-and-routing/tasks.md`. Keep the
analyzer seam intact (no vendor SDKs in routing/dispatch), keep the scripted `mock` backend
deterministic, and update `HACKATHON.md` §3.6 as Kiro features are used.

## License
Released under the **MIT License** — see [`LICENSE`](./LICENSE). Third-party components
and their licenses are recorded in [HACKATHON.md](./HACKATHON.md) §4.
