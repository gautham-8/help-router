# Agent Brief: Hackachusetts Submission Compliance

> **Instructions to the agent:** Read this whole document. Your job is to (1) create `HACKATHON.md` at the repo root, based on the template in Part 4, (2) make sure the repo structure satisfies every requirement in Parts 1-3, and (3) keep `HACKATHON.md` updated as we build, so the Kiro write-up is accurate and evidence-backed at submission time. Do not invent usage that did not happen. Every claim in the Kiro write-up must point to a real file or workflow in this repo.

---

## Part 1: Hard requirements (disqualification risks)

These are pass/fail. Verify each one before every push and again before submission.

| # | Requirement | How to satisfy in the repo |
|---|-------------|----------------------------|
| 1 | **Must use Kiro to build the project.** "Insufficient use of Kiro" = disqualification at judges' sole discretion. | Build through Kiro (IDE/CLI/Web/Crew). Use specs, hooks, steering, MCP, PBT, powers (see Part 3). Keep evidence committed. |
| 2 | **`.kiro/` directory at the repo root, committed.** | Never add `.kiro` or any subfolder to `.gitignore`. Run `git check-ignore -v .kiro` and confirm no output. Run `git ls-files .kiro` and confirm files are tracked. |
| 3 | **Public GitHub repository** with all source code, assets, and instructions needed for the project to function. | Repo is public. README contains setup/run instructions. No missing env files, models, or assets (provide `.env.example`). Never commit real secrets. |
| 4 | **Max 4 team members**, all added on the submission form. | Team list recorded in `HACKATHON.md`. One designated Representative submits. |
| 5 | **One challenge track identified**: Healthcare & Biotech, Robotics (& Hardware), Climate Tech (& Clean Energy), or Civic Action (Civic Services). | State the track at the top of `HACKATHON.md` and README. |
| 6 | **Text description** of features and functionality. | "Project Description" section in `HACKATHON.md`; mirror in README. |
| 7 | **Demo video under 3 minutes**, shows the project functioning on its target device, public on YouTube/Vimeo/Facebook Video/Youku. No third-party trademarks or copyrighted music/material without permission. | Link placed in `HACKATHON.md` and README. Use no copyrighted music, no logos we don't own. |
| 8 | **Kiro write-up** explaining how Kiro was used. | "How We Used Kiro" section (Part 4). |
| 9 | **Original work**, solely owned by the team, no IP infringement. Open source allowed if licenses are followed and we build meaningfully on top of it. | Add a `LICENSES`/"Third-party" section listing every dependency, dataset, and asset with its license. |
| 10 | **English** for all materials (or provide translations). | All docs in English. |
| 11 | **Working project accessible for testing**, free, no restrictions, until judging ends. If private, include login credentials in the testing instructions. | Provide a live URL, demo, or test build. Put credentials (test accounts only) in "Testing Instructions". |
| 12 | **No changes after the Submission Period ends.** | Freeze the repo at submission. Tag a release (e.g. `v1.0-submission`). |
| 13 | **No financial or preferential support** from the Sponsor/Administrator for the project. | Note in `HACKATHON.md` that none was received. |

---

## Part 2: How we are judged (optimize for this)

Three criteria. `HACKATHON.md` should make each one easy to score.

1. **Potential Value:** Real, clearly defined problem; scalable and realistic; accessibility, equity, adoption; who benefits and how it scales beyond the hackathon; how unique vs. saturated the market is.
2. **Implementation (Kiro usage):** Thoughtful strategy; variety of Kiro tools (IDE, CLI, Web, Crew); depth of understanding of each feature; experimentation and strategic decisions; integrations beyond the basics.
3. **Quality and Design:** Creativity, originality, polished and intuitive UI; unique public datasets; surprising combinations of technology.

**Bonus prize: Best Use of Kiro** goes to the highest Implementation score within the top 10% of projects. So the Kiro write-up and the visible `.kiro` evidence matter a lot. A project can win one Overall Prize per category plus up to two Bonus Prizes.

---

## Part 3: Required `.kiro/` structure and what each piece must show

Create and actively use the following. Everything must be committed. Prefer real, meaningful content over boilerplate; judges will read these files.

```
.kiro/
├── specs/                  # Spec-driven development
│   └── <feature-name>/
│       ├── requirements.md # User stories + acceptance criteria (EARS-style: WHEN ... THE SYSTEM SHALL ...)
│       ├── design.md       # Architecture, data models, interfaces, correctness properties (for PBT)
│       └── tasks.md        # Discrete, trackable implementation tasks
├── steering/               # Persistent project context
│   ├── product.md          # Product purpose, users, domain rules, accessibility goals
│   ├── tech.md             # Stack, libraries, conventions, testing approach
│   └── structure.md        # Repo layout and naming conventions
├── hooks/                  # Agent hooks (event-triggered automations)
└── settings/
    └── mcp.json            # MCP server configuration (no secrets; use env vars)
```

> Note: exact file names and formats can differ by Kiro version. Use what Kiro generates; check Kiro's docs and match its current conventions rather than hand-forcing the layout above.

### 3.1 Spec-driven development
- Write at least one substantial spec per major feature (ideally several). Let Kiro generate and iterate on `requirements.md` → `design.md` → `tasks.md`, then execute tasks from `tasks.md`.
- Record in `HACKATHON.md`: how the specs were structured, how the approach improved development vs. "vibe coding", and at least one concrete example where spec-driven work beat or differed from vibe coding (e.g., a bug avoided, a requirement caught early, a refactor made safe).
- If we also vibe-coded anything, say so honestly and compare.

### 3.2 Agent hooks
- Build real automations that solve real friction. Ideas: run tests/lint on file save; regenerate docs or types when a schema changes; check that `.kiro` is not gitignored; update `HACKATHON.md`'s Kiro log after spec completion; security/secrets scan before commit; accessibility check on UI file save.
- For each hook, document: trigger, action, and measurable benefit.

### 3.3 Steering docs
- Write steering files that materially change Kiro's output (domain vocabulary, coding standards, accessibility rules, testing rules, "never do X").
- Consider conditional/file-match steering for specific areas (e.g., UI vs. backend) if Kiro supports it in this version.
- Record which steering strategy made the biggest difference, with a before/after example if possible.

### 3.4 MCP
- Add at least one MCP server that unlocks something otherwise hard (e.g., a docs server, a database/API server, a domain data source, GitHub, a browser/test server relevant to the track).
- Document: which server(s), why, what workflow it enabled, and what would have been difficult or impossible without it. Keep secrets out of `mcp.json`.

### 3.5 Property-based testing (PBT)
- Identify requirements with universal invariants (parsing, validation, calculations, round-trips, state machines, eligibility rules, unit conversions) and enable PBT for them. Capture the properties in `design.md` and implement with a PBT library (e.g., `hypothesis` for Python, `fast-check` for TypeScript/JS).
- Record: which requirements got PBT, any bugs PBT caught that unit tests missed (include the shrunk counterexample if there is one), and what we fixed.

### 3.6 Kiro powers
- Install and use relevant Kiro powers (bundled best practices/tooling) for our stack or track. Document which ones, what expertise they brought, and any third-party tools/integrations we would not otherwise have used.

### 3.7 Kiro tools variety
- Try more than one surface where it makes sense (Kiro IDE, CLI, Web, Crew). Document which we used, for what tasks, and how they differed.

---

## Part 4: Create `HACKATHON.md` using this template

Create `HACKATHON.md` at the repo root. Fill in what we know now; leave clearly marked `TODO:` placeholders for the rest, and ask the humans for anything you cannot determine from the repo. Do not fabricate.

````markdown
# <Project Name>

**Hackathon:** Hackachusetts
**Track:** <Healthcare & Biotech | Robotics & Hardware | Climate Tech & Clean Energy | Civic Services/Action>
**Demo video (<3 min):** <public YouTube/Vimeo/Facebook Video/Youku URL>
**Live demo / test build:** <URL or instructions>
**Repository:** <public GitHub URL>

## Team (max 4)
| Name | Role | Representative? |
|------|------|-----------------|
| TODO | TODO | Yes/No |

## 1. Project Description
<What it is, the problem, who it helps, key features and functionality. Plain English, scannable.>

### Potential Value
- **Problem & who is affected:** ...
- **How it's scalable and realistic:** ...
- **Accessibility, equity, adoption:** ...
- **Market landscape (what exists, how this differs):** ...
- **Path beyond the hackathon:** ...

### Quality and Design
- **What's original/creative:** ...
- **Public datasets / unique resources used:** ...
- **UI/UX decisions:** ...

## 2. Testing Instructions
1. Prerequisites: ...
2. Setup: `...`
3. Run: `...`
4. Test accounts / credentials (if the site is private): ...
5. How to run the test suite (including property-based tests): `...`

## 3. How We Used Kiro

### 3.1 Kiro tools used
<IDE / CLI / Web / Crew: what we used each for and how they differed.>

### 3.2 Spec-driven development
- Specs: link each (`.kiro/specs/<name>/`)
- How we structured them:
- How it improved our process vs. vibe coding (with a concrete example):

### 3.3 Agent hooks
| Hook (`.kiro/hooks/...`) | Trigger | What it automates | Benefit |
|---|---|---|---|

### 3.4 Steering docs
- Files (`.kiro/steering/...`) and what each does:
- The strategy that made the biggest difference (before/after example):

### 3.5 MCP
- Servers (`.kiro/settings/mcp.json`):
- Features/workflows enabled that would've been hard or impossible otherwise:

### 3.6 Property-based testing
- Requirements with PBT enabled:
- Library/tooling:
- Issues PBT caught that unit tests would likely have missed (include counterexamples):

### 3.7 Kiro powers
- Powers used and what best practices/expertise they provided:
- Third-party tools/integrations we wouldn't otherwise have used:

### 3.8 Kiro usage log (chronological, keep appending)
| Date | Kiro feature | What we did | Outcome |
|---|---|---|---|

## 4. Third-Party Materials & Licenses
| Item | Type (library/dataset/asset) | License | Used how |
|---|---|---|---|

Confirm: all code is original or properly licensed; no third-party trademarks or copyrighted music in the demo video; no financial/preferential support from the Sponsor or Administrator.

## 5. Submission Checklist
(see below; keep this list current)
````

Also add to **README.md**: project summary, track, demo video link, setup and run instructions, test instructions, and a link to `HACKATHON.md`.

---

## Part 5: Pre-submission checklist (agent: verify and report pass/fail)

- [ ] Repo is public and cloneable by a stranger
- [ ] `/.kiro` exists at root and is tracked in git (`git ls-files .kiro` non-empty)
- [ ] `.gitignore` contains no `.kiro` entries (`git check-ignore -v .kiro` returns nothing)
- [ ] `.kiro/specs/` has real, complete specs (requirements, design, tasks)
- [ ] `.kiro/steering/` has meaningful steering files
- [ ] `.kiro/hooks/` has working hooks, each documented
- [ ] `.kiro/settings/mcp.json` configured, with no secrets committed
- [ ] PBT implemented and passing; results documented
- [ ] Kiro powers used and documented
- [ ] README has setup/run/test instructions; project runs from a clean clone
- [ ] `.env.example` provided; no secrets in git history
- [ ] `HACKATHON.md` fully filled in, no `TODO:` left, every Kiro claim backed by a file path
- [ ] Track stated
- [ ] Demo video: under 3 minutes, shows the app working on its target device, public, no copyrighted music/trademarks, link in repo and submission form
- [ ] Third-party licenses documented
- [ ] Team (max 4) added on the form; Representative designated
- [ ] Release tagged and repo frozen at submission time

---

## Part 6: Working rules for the agent

1. **Honesty over polish.** If a feature (e.g., a hook, MCP server, power) isn't actually used yet, list it under "Still to do" and tell the humans, rather than writing it up as done.
2. **Evidence-first.** Link to concrete files, commits, and examples.
3. **Update as we go.** After each spec is completed, hook added, steering file changed, or MCP/power installed, append an entry to the Kiro usage log in `HACKATHON.md`.
4. **Never touch `.gitignore` in a way that excludes `.kiro`.** If a template or tool tries to, stop and flag it.
5. **Ask before guessing** on team names, track choice, project name, video URL, and live demo URL.
6. **Report back** with the checklist status and a short list of gaps whenever asked, and always before the final submission.