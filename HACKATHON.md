# Help Router

**Hackathon:** Hackachusetts
**Track:** Civic Services / Civic Action
**Demo video (<3 min):** TODO: public YouTube/Vimeo/Facebook Video/Youku URL
**Live demo / test build:** TODO: URL (runs locally from a clean clone with no keys; see Testing Instructions)
**Repository:** https://github.com/gautham-8/hackachusetts-2026

## Team (max 4)
| Name | Role | Representative? |
|------|------|-----------------|
| TODO | TODO | Yes/No |
| TODO | TODO | No |

> Agent note: team names/roles not yet provided. Ask the humans and fill in before submission.

## 1. Project Description

Help Router turns one spoken word into a routed emergency report. A person in
distress says "Help"; their phone records the next 60 seconds of audio together with
their location; the system works out which service is needed — police, fire, medical,
or several at once — and delivers the details to that service's live dispatch queue,
where a human responder confirms every dispatch.

The problem: in an emergency a person under stress often does not know which number to
call, cannot talk for long, and may not be able to say where they are. The first
minute holds the most evidence, and it is usually lost.

**Key features**
- One-tap capture: a single "Help" button records 60 seconds of audio in ~10-second
  chunks and captures location, with no further input from the caller.
- Multi-signal understanding: speech transcription + audio-event detection (screams,
  breaking glass, sirens, smoke alarms) + a language-model router that fuses both into
  a set of services, each with a confidence.
- Provisional then refined routing: a route appears provisionally after ~10 seconds
  and sharpens as more audio arrives over the full minute.
- Three-queue dispatch dashboard (police / fire / medical) updating live; a report can
  appear in several queues at once.
- Human-confirmed dispatch: a responder confirms or rejects every report. Nothing is
  auto-dispatched, and the demo never contacts a real emergency service.

### Potential Value
- **Problem & who is affected:** anyone facing an emergency who freezes, can't speak
  long, doesn't know the right number, or can't describe their location — including
  people with disabilities, language barriers, or in a situation where talking is
  unsafe.
- **How it's scalable and realistic:** the analyzer seam lets the same routing logic
  run on cheap deterministic rules for the demo and on production speech/audio/LLM
  models in the field; queues and dashboards are per-service and horizontally simple.
- **Accessibility, equity, adoption:** one-tap operation, large high-contrast control,
  screen-reader labels, honest status at each step, no knowledge of jurisdiction or
  phone numbers required, free to run without paid APIs.
- **Market landscape (what exists, how this differs):** TODO: brief comparison to
  existing panic-button and E911 location apps; our differentiator is multi-service
  confidence routing with a provisional→refined loop and audio-event evidence, not
  just a location ping.
- **Path beyond the hackathon:** wire the `live` server-side adapters (and an LLM router)
  behind the existing seam; pilot with a campus or municipal dispatch desk using the human-confirm
  dashboard as the integration point.

### Quality and Design
- **What's original/creative:** fusing audio *events* (not just words) with a
  transcript into a confidence-weighted set of services, and treating routing as a
  provisional→refined state machine with a monotonic-commitment guarantee.
- **Public datasets / unique resources used:** Google's **YAMNet** sound classifier
  (trained on the public **AudioSet** ontology; 521 classes), vendored in the repo and run
  on the caller's device with TensorFlow.js, so sound detection works offline. Licenses in §4.
- **UI/UX decisions:** one-tap caller screen vs. a calm three-column responder board;
  provisional/refined badges; a persistent demo-safety banner.

## 2. Testing Instructions
1. **Prerequisites:** Python 3.11+, Node 22.12+. No API keys needed.
2. **Setup** (full steps in the README):
   - `cp .env.example .env` (optional; defaults work; read from the repo root)
   - Backend: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   - Frontend: `cd frontend && npm install`
3. **Run** (two terminals):
   - Backend: from `backend/`, `.venv/bin/uvicorn app.main:app --reload --port 8000`
   - Frontend: from `frontend/`, `npm run dev`
   - Responder first: <http://localhost:5173/dashboard>.
   - Caller: <http://localhost:5173/>. Allow the microphone, press Help, and say "there is a
     fire in my kitchen" or play a smoke-alarm sound near the mic (Chrome or Safari for
     speech). There is nothing to choose. The report appears in the matching queue(s), or
     in **Triage** if the system cannot tell.
   - Shortcut for a quick check: add `?chunkMs=2000` to the caller URL (about 12 s).
   - Repeatable run with no microphone: <http://localhost:5173/?demo=1&chunkMs=2000>, pick a
     scripted scenario, press Help.
   - On a phone: `npm run dev:phone` and open `https://<laptop-ip>:5173` (HTTPS is
     required for the microphone).
4. **Test accounts / credentials:** none. The demo is open and local. If you expose it
   anywhere else, set `DASHBOARD_TOKEN` (see the README's security notes).
5. **Run the checks:**
   - Backend (from `backend/`): `.venv/bin/python -m pytest` (unit + Hypothesis property
     tests + integration), `.venv/bin/ruff check app tests`, `.venv/bin/mypy app`.
   - Frontend (from `frontend/`): `npm run typecheck`, `npm run test`, `npm run build`.

> **Verified results** (2026-10-24; the test counts below were re-run on a clean copy of the
> tree after `npm ci` and `pip install`, with a root `.env` present):
> - Backend: `149 passed` (83 unit, 11 property, 55 integration); `ruff` and `mypy` clean.
> - Frontend: `tsc` clean; `43 passed`, including `fast-check` properties and the **real
>   vendored YAMNet model run on generated audio** (silence yields no events; a smoke-alarm
>   beep pattern is detected above 50%; a siren-style wail is flagged as an alarm sound);
>   production build succeeds; `npm audit` reports 0 vulnerabilities.
> - **Real Chrome, end to end** (headless Chrome driven by a throwaway script, not committed;
>   the microphone was replaced by a synthetic `MediaStream`): no scenario picker is shown;
>   `MediaRecorder` chunks are decoded and classified by YAMNet in the page, sent over the
>   WebSocket, routed, and shown on the dashboard. Smoke-alarm audio went to **Fire**
>   (74-89%); silence and a bare alarm tone with no words went to **Triage**; sending a
>   triage item to Medical moved it and recorded who did it; confirming works; demo mode
>   routes `multi-service` to all three queues while never calling `getUserMedia`.
> - The dev servers serve `/` and `/dashboard`; `wss://` works through the HTTPS phone mode.
>
> **Not verified:**
> - **Physical microphone hardware, and speech recognition accuracy.** Headless Chrome's
>   speech recognition returned made-up phrases from non-speech audio ("want to shoot at an
>   estimate"), so speech output is **unreliable and can hallucinate words that trigger
>   routing**. It has not been tested with real human speech, on a phone, or in Safari.
> - Chrome's file-fed fake microphone (`--use-file-for-fake-audio-capture`) produced silence
>   in this environment for every WAV variant tried, so a synthetic WebAudio stream was used
>   instead. The audio-to-classifier path is therefore verified; the hardware-to-browser
>   step is not.
> - Whether speech recognition and `getUserMedia` can run at the same time on every phone
>   (they may compete for the microphone on some mobile browsers).
> - Nothing has been cloned from GitHub yet; the clean-copy run used the working tree.
> - No live deployed URL exists yet (requirement #11).
> - The sound classifier's accuracy on real emergencies is unmeasured. We only checked
>   synthetic tones; real screams and breaking glass have not been tested.

### Honest scope
- **What was wrong before:** the first version could only route a scenario the user *picked*;
  nothing analyzed the caller's voice or sounds, and the pitch ("press Help and it works out
  the service") was not true. The picker was a stand-in for missing analysis. That is fixed
  in the default mode (tasks 23-29 in `tasks.md`); the picker now exists only in `?demo=1`.
- **Speech** is transcribed by the *browser's* speech service (Chrome: Google; Safari:
  Apple), not by us, so audio may leave the device for that step. This app receives only text.
  It is unavailable in some browsers, and the UI says so.
- **Sounds** are classified on the device by YAMNet, mapped to six event kinds. Accuracy on
  real emergencies is untested, and per the model card YAMNet's scores are **not calibrated
  probabilities**, so our 0.25 cut-off and the rule weights built on those scores are rough
  choices, not tuned values.
- **Routing** is a hand-written rule table (keywords + sounds) with a deliberately narrow
  negation rule, not a trained model or an LLM. The original pitch mentioned an LLM router;
  that is still the `live` seam and is not built.
- **`ANALYZER_BACKEND=live` is not implemented.** Its speech and sound adapters raise
  `NotImplementedError`; selecting it with no keys fails at report creation with a clear 503.
- **Device-supplied signals are unauthenticated claims.** A hostile client can send a fake
  smoke alarm. The control is that a human confirms every dispatch.
- **Storage** is in memory (500 reports max, lost on restart), and with no `DASHBOARD_TOKEN`
  the API is open.
- **Found by testing in a real browser, not by the spec or unit tests:** a report the system
  could not classify was flagged `needs_attention` but shown to **no** responder, while the
  caller saw "Sent to dispatch". It now goes to a Triage queue (Requirement 5.8-5.9).

## 3. How We Used Kiro

### 3.1 Kiro tools used
- **Kiro IDE (spec-driven):** authored steering docs and the full spec
  (requirements → design → tasks), then executed the tasks — scaffolding the backend
  and frontend, running the test suites, and iterating on failures — all inside the
  IDE agent loop.
- **Agent hooks:** created via the IDE (see §3.3).
- TODO: note CLI / Web / Crew usage if/when used, and how they differed.

**Backends:** `browser` (default; device-supplied signals), `mock` (scripted scenarios for
demo mode and tests), `live` (server-side models, not implemented). All use the same
`Transcriber` / `AudioEventDetector` / `Router` protocols and the same rule router.

**Live-backend plan:** `backend/app/analyzers/live/` holds adapters implementing those
protocols.
`LiveTranscriber` and `LiveAudioEventDetector` are integration seams that raise a clear
error until a provider SDK is wired and the relevant `.env` keys are set;
`LiveRouter` currently reuses the deterministic rule-table fusion so routing still
satisfies the router properties (P1–P6, P8–P11) the moment real transcription/detection
are connected. Selecting the backend is a one-line env change
(`ANALYZER_BACKEND=live`); no downstream code changes. A live backend with missing keys
fails at report creation with a 503 and a clear message.

Known wart in the seam: `backend/app/main.py` imports the demo-scenario loader
(`list_scenarios`, `get_scenario`) straight from `analyzers/mock`, because scenarios are
a demo feature. `routing/` and `dispatch/` stay clean; moving the scenario list behind
the factory would finish the job.

### 3.2 Spec-driven development
- Specs: `.kiro/specs/help-capture-and-routing/` (`requirements.md`, `design.md`,
  `tasks.md`).
- How we structured them: EARS-style acceptance criteria per requirement; the design
  pins down the analyzer seam, the routing rule table, the state machine, and a named
  list of correctness properties (P1–P8) that feed property-based testing; tasks are
  discrete and reference the requirements they satisfy.
- How it improved our process vs. vibe coding: naming the correctness properties in
  `design.md` before coding meant the router was written against them and the first
  property tests fell out directly. We also keep an honest record of where that was
  *not* enough:
  1. **A scenario fixture didn't satisfy its own requirement.** Requirement 6.3 says
     "car crash with injuries → police + medical", but the first fixture's signals only
     cleared the medical threshold. The scenario test failed and we strengthened the
     fixture rather than weakening the requirement. Spec-first turned the gap into a
     failing test instead of a demo-day surprise.
  2. **The first version of our own tests were weaker than they looked.** A review pass
     (tasks 16-22 in `tasks.md`) found that the original "monotonic commitment" property
     (P5) could never fail: the additive router never lowered a confidence, so nothing
     could be dropped, and the matching "downgrade note" code was unreachable. We had
     papered over this by rewriting a failing unit test to fit the code. The fix was a
     design change (confidence now decays when evidence stops, per Requirement 4.9) and
     a P5 that generates thresholds so the keep-despite-threshold branch actually runs.
     Lesson recorded in `steering/tech.md`: check that a property can fail.
  3. **Specs did not catch everything; review did.** Real bugs shipped through the spec
     and its tests: the `/dashboard` page was shadowed by a WebSocket proxy rule, the
     caller never sent `end`, a rejected report reappeared on the next chunk, and
     keyword matching fired inside words ("begun" → police). Each now has a failing-
     first test and a requirement (4.7-4.10, 5.5, 6.5-6.6, 7). This is a vibe-coding
     style failure mode we did not avoid; the spec's value here was giving the review a
     checklist to extend.

### 3.3 Agent hooks
| Hook (`.kiro/hooks/...`) | Trigger | What it automates | Benefit |
|---|---|---|---|
| `guard-kiro-tracked.json` | PreToolUse (`fs_write`/`str_replace`/`fs_append`) | Runs `git check-ignore .kiro`; blocks the write (exit 2) if `.kiro` ever becomes gitignored | Protects hard submission requirement #2 automatically, before a bad write lands |
| `backend-tests-on-save.json` | PostFileSave (`backend/.*\.py$`) | Runs `pytest` in `backend/` (using `backend/.venv` if present) on every backend Python save | Catches router / state-machine regressions the moment a file is saved |

> Honest note: the first version of `backend-tests-on-save` called the system `python`,
> which has no FastAPI installed, so it could never have passed. The review caught it
> and it now prefers `backend/.venv/bin/python`. Neither hook has been observed firing
> in the IDE yet (hooks load on the next session start); treat their benefit as
> expected, not measured.

### 3.4 Steering docs
- Files (`.kiro/steering/...`): `product.md` (purpose, users, domain rules such as
  demo-safety and human-in-the-loop, accessibility goals), `tech.md` (stack and the
  all-important analyzer seam + testing approach), `structure.md` (repo layout and
  naming).
- The strategy that made the biggest difference: the **analyzer-seam rule** in
  `tech.md` ("routing, dispatch, and the WebSocket layer import the protocols, never a
  vendor SDK"). The result is visible in the code: `backend/app/routing/` and
  `backend/app/dispatch/` import only `app.analyzers.interfaces` and domain models, and
  switching `ANALYZER_BACKEND=browser|mock|live` in `factory.py` changes nothing downstream.
  The `live` adapters (`backend/app/analyzers/live/`) are drop-in implementations of
  the same three protocols. This is what lets the whole app and test suite run with no
  API keys while leaving a clean path to real models.

### 3.5 MCP
- Servers (`.kiro/settings/mcp.json`): TODO — e.g. a documentation server for the AI
  SDKs used by the live backend, or a GitHub server.
- Features/workflows enabled: TODO.

### 3.6 Property-based testing
- Requirements with PBT enabled: 3.1, 3.2, 3.3, 3.4, 3.5, 4.2, 4.4, 4.6 (properties
  P1–P11 in `design.md`).
- Library/tooling: `hypothesis` (Python) for the backend router and state machine
  (`backend/tests/property/`, 11 tests); `fast-check` (TypeScript) for the client-side
  helpers (`frontend/tests/route.test.ts`, `frontend/tests/timing.test.ts`).
- What PBT covers that example tests do not: P1 (confidences stay in `[0, 1]`), P4 (every
  routed service is justified), P5 (a committed service is never dropped, quantified over
  generated thresholds and priors) and P7 (the state machine accepts exactly the
  one-step-forward moves) are claims over all inputs, not a handful of examples. The
  property transcripts mix keyword soup with arbitrary text so unexpected input is
  exercised too.
- **Did PBT find real bugs? Honestly: not by itself.** No `hypothesis` run produced a
  shrunk counterexample against the shipped code. The bugs we found came from code
  review and from running the real servers (see §3.2). The useful PBT lesson was the
  reverse: the first P5 and P7 passed trivially, which we only noticed in review.
- **Mutation check (2026-10-24).** To prove the properties can fail, we hand-broke the
  router five ways on a scratch copy and ran `tests/property`. Each was caught by the
  intended property: dropping the committed-service branch → P5; removing word
  boundaries → P9; removing decay → P10; a faint smoke alarm pinning fire → P11 (added
  because no property caught this mutant at first); smoke alarm no longer pinning →
  P2 and P8. This was a manual one-off, not an automated mutation-testing tool.

### 3.7 Kiro powers
- Powers used: TODO.
- Third-party tools/integrations we wouldn't otherwise have used: TODO.

### 3.8 Kiro usage log (chronological, keep appending)
| Date | Kiro feature | What we did | Outcome |
|---|---|---|---|
| 2026-10-24 | Steering | Wrote `product.md`, `tech.md`, `structure.md` establishing the demo-safety rule, the analyzer seam, and repo layout | Persistent project context for all later work |
| 2026-10-24 | Spec | Authored `help-capture-and-routing` spec (requirements → design → tasks) with EARS criteria and PBT properties P1–P8 | Clear, testable plan before any code |
| 2026-10-24 | Hooks | Created `guard-kiro-tracked` and `backend-tests-on-save` hooks | Automated compliance guard + tests-on-save |
| 2026-10-24 | Spec execution | Implemented backend tasks 1–10: domain models, forward-only state machine, analyzer seam, deterministic mock backend + 4 scenarios, dispatch queues, FastAPI + WebSocket app | `29 passed` (incl. 8 Hypothesis property tests); `ruff` clean; backend serves `/health`, `/scenarios`, `/reports` |
| 2026-10-24 | Spec execution | Implemented frontend tasks 11–13: caller PWA (one-tap capture, scenario picker, live status, demo banner) and three-queue dispatch dashboard over WebSocket | `tsc` clean; `2 passed` (incl. a `fast-check` property test); production build succeeds |
| 2026-10-24 | Spec execution | Implemented live-backend adapters (task 14) behind the same protocols | Clean seam to real models; selected via `ANALYZER_BACKEND=live`. Speech and audio-event adapters are unimplemented seams |
| 2026-10-24 | Code review + spec update | Reviewed everything written so far by running probes against the real code and dev servers; found 14 issues (dashboard page 404, `end` never sent, rejected reports reappearing, in-word keyword matches, ignored root `.env`, unusable tests-on-save hook, unsafe-by-default API, trivially-passing properties, and more). Updated requirements (4.7-4.10, 5.5, 6.5-6.6, new R7), design (rule table, API, P1-P11), and tasks 16-22 | Each fix has a test that failed first |
| 2026-10-24 | Spec execution | Implemented tasks 16-22: `/ws` routes, real chunked audio capture, hardened stream, sticky rejection, decay/pinning/negation in the router, `DASHBOARD_TOKEN`, repo-root `.env`, vite 8 / vitest 5 upgrade | Backend `109 passed`, frontend `17 passed`, `npm audit` 0, clean-copy run green |
| 2026-10-24 | Conversation / spec | You pointed out that making the user pick a scenario contradicted the product. I agreed (the analysis half was a mock), proposed three options with costs, and implemented the free on-device one: requirements R8, design, tasks 23-29 | Pressing Help now needs no choices; scenario picker moved to `?demo=1` |
| 2026-10-24 | Verification in a real browser | Drove headless Chrome with a synthetic microphone through the whole pipeline. Found the model's three outputs are in no promised order (read the wrong one first), that Chrome's file-fed fake mic yields silence here, and that an unclassifiable report was invisible to responders | Fixed the output selection; added a Triage queue (R5.8-5.9); documented what remains unverified |
| 2026-10-24 | Property-based testing | Hand-mutated the router five ways to check the properties can fail; found one mutant no property caught and added P11 | All five mutants now caught |

## 4. Third-Party Materials & Licenses
| Item | Type (library/dataset/asset) | License | Used how |
|---|---|---|---|
| FastAPI | library | MIT | Backend HTTP/WebSocket |
| Pydantic | library | MIT | Domain models/validation |
| Uvicorn | library | BSD-3-Clause | ASGI server |
| pytest | library | MIT | Testing |
| Hypothesis | library | MPL-2.0 | Property-based testing |
| pydantic-settings, websockets, httpx, ruff, mypy | libraries | MIT / BSD (TODO: verify each from its package metadata) | Config, WebSocket support, test client, lint, types |
| React / React DOM | library | MIT | Frontend UI |
| Vite, Vitest | library | MIT | Frontend build, dev server, tests |
| @vitejs/plugin-react, @vitejs/plugin-basic-ssl | library | MIT | React transform; self-signed HTTPS for phone testing |
| @testing-library/react, jsdom, fast-check | library | MIT | Component tests, DOM for tests, property tests |
| TypeScript | library | Apache-2.0 | Frontend language |
| @tensorflow/tfjs 4.22.0 | library | Apache-2.0 | Runs YAMNet in the browser |
| YAMNet (TF.js graph model from TF Hub, `google/tfjs-model/yamnet/tfjs/1`) | model, vendored in `frontend/public/models/yamnet/` | Source code Apache-2.0 (verified in tensorflow/models). TODO: the TF Hub page states no separate license for the weight files; confirm before relying on it past the hackathon | On-device sound-event classification |
| `yamnet_class_map.csv` (from tensorflow/models, `research/audioset/yamnet`) | label list, vendored | Names come from the AudioSet ontology, **CC BY-SA 4.0** (verified on Google's AudioSet page); attribution is in `frontend/public/models/yamnet/README.md` | Maps class numbers to names |
| Web Speech API | browser feature, not shipped by us | n/a | Speech-to-text, provided by the user's browser vendor |
| TODO (live backend model SDKs / datasets) | TBD | TBD | Only if the `live` backend is used |

Confirm: all code is original or properly licensed; no third-party trademarks or
copyrighted music in the demo video; no financial/preferential support from the
Sponsor or Administrator was received.

## 5. Submission Checklist
- [x] `.kiro/` exists at root and is tracked in git
- [x] `.gitignore` contains no `.kiro` entries
- [x] `.kiro/specs/` has a real spec (requirements, design, tasks)
- [x] `.kiro/steering/` has meaningful steering files
- [x] `.kiro/hooks/` has working hooks, each documented
- [ ] `.kiro/settings/mcp.json` configured, no secrets committed (blocked: path write-protected in this environment; configure via Kiro's MCP UI)
- [x] PBT implemented and passing; results documented
- [ ] Kiro powers used and documented
- [x] README has setup/run/test instructions
- [ ] Project runs from a clean clone: verified on a clean copy of the tree (install, tests, build all pass), but not yet from a real `git clone` because nothing is committed or pushed
- [ ] Real microphone/geolocation capture verified on the target phone (HTTPS mode)
- [x] `.env.example` provided; `.env` is gitignored
- [ ] No secrets in git history (nothing committed yet; re-check before the first push)
- [ ] Repo is public and cloneable by a stranger
- [ ] `HACKATHON.md` fully filled in, no `TODO:` left, every Kiro claim backed by a file path
- [x] Track stated (Civic Services / Civic Action)
- [ ] Demo video under 3 minutes, public, no copyrighted music/trademarks, linked here and on the form
- [ ] Third-party licenses documented (complete when deps are finalized)
- [ ] Team (max 4) added on the form; Representative designated
- [ ] Release tagged and repo frozen at submission time
