# CareerOS · agent-powered career growth for students and recent graduates (v0.2.0)

[中文 README](README.md) · [MIT License](LICENSE)

CareerOS is a local-first workbench primarily for students and recent graduates.
Start with an uncertain direction, a course project, an internship or an informal
responsibility. Across sessions, your chosen agent builds an evidence-backed
understanding of you and helps turn exploration into learning, application plans
and interview preparation at a pace that fits your studies.

It keeps the
*semantic* work — reading a JD, mapping your real experience to it, arguing with
your own resume — with an agent, and keeps everything that must be reproducible
(versions, provenance, state) in a deterministic Python CLI over SQLite.

Eight skills wrap one loop: discovery → mapping → sourcing → JD analysis →
evidence-locked resume → simulated hiring review → feedback → next action.

**Core CLI: no third-party runtime dependencies.** Python 3.10+ and the standard library.
The additional `document-export` skill converts an existing resume or reviewed plan
into editable DOCX and PDF. It changes format only and writes no CareerOS record.

The workflow is independent of the agent vendor: Claude Code (CC), WorkBuddy,
Doubao or another LLM-backed tool can follow the repository instructions. Direct
execution requires local file access and a terminal; chat-only tools require the
user to run commands and share selected outputs. Native Skills discovery and
browser capabilities vary, and individual tools have not all been integration-tested.
If a tool does not discover Skills automatically, ask it to read `AGENTS.md` and
the relevant `.agents/skills/<name>/SKILL.md` explicitly.

New here? Read the separate [User onboarding manual](docs/USER_GUIDE.md) (Chinese)
for setup, the first conversation, study/application planning and switching tools.

## This project will not apply to jobs for you

> **海投是负期望的。 / Mass applying has negative expected value.**

So CareerOS is a *desk before the application*, not an application bot. It does the
things that actually raise the expected value of a single application: decomposing
requirements, aligning evidence, freezing resume versions, recording real feedback.
The submit click stays with you, on the employer's own page.

Deliberately absent: no submit API, no browser auto-clicking, no CAPTCHA bypass,
no bulk-apply queue. An optional search extension may use locally configured
credentials; see the extension's documentation. The final submission stays human.

## Architecture in one paragraph

A Career Twin Core (`careeros/core/`) is the single versioned store of user state:
assertions with provenance and confidence, goals, pipeline status, actions,
signals, context budgets, reflection proposals. Skills read a bounded context brief
at the start of a session and write back through one path per claim. Facts,
user-confirmed evidence, model inference and unverified claims are kept as distinct
kinds — an inference cannot silently become a resume line. Deterministic code
computes state; the model argues about meaning. See
[docs/CAREER_TWIN_CORE_ARCHITECTURE.md](docs/CAREER_TWIN_CORE_ARCHITECTURE.md)
(Chinese).

## Quick start

Clone or download the repository, load the project folder in your agent tool,
and allow project file access and local command execution. Then send:

```text
Read AGENTS.md and follow the first-use startup workflow for CareerOS.
I am a [student/recent graduate], currently [exploring roles/seeking an internship/preparing applications].
Start with one real experience and ask two or three questions at a time.
Keep facts, inferences and unknowns separate, then save the records and one agreed next action.
```

The agent checks the runtime, resolves a Python 3.10+ interpreter and initializes
the local database. The core needs no package installation or extra service.
Missing runtime or execution permissions must be reported explicitly. The
[user manual](docs/USER_GUIDE.md) includes an optional isolated fictional demo.

## What it can and cannot do

| Can | Cannot |
| --- | --- |
| Read public Greenhouse/Lever boards, parse single company job pages (JSON-LD first) | Log in to job boards, or scrape behind a login |
| Import JSON/CSV, keep immutable job snapshots, group one vacancy across platforms | Submit applications, message recruiters, bypass CAPTCHAs |
| Build evidence-constrained Markdown resumes with frozen JD/resume versions | Invent schools, employers, durations or achievements |
| Run a seven-stage simulated hiring review (ATS → competition) | Predict offers; A–D are local simulations, not employer verdicts |
| Track application channel, schedule, status and actual/mock/hypothesis feedback | Auto-advance status or auto-raise a grade after feedback |

Company research keeps `fact` and `inference` separate with a URL and retrieval
date; a `fresh` timestamp only means the source was checked recently, never that
the vacancy is still open.

## Optional extensions

`careeros/extras/` holds integrations that are **never imported on the default
path**. They call third-party endpoints whose terms are the user's responsibility:

- `careeros/extras/liepin.py` — Liepin job search, off unless
  `CAREEROS_ENABLE_LIEPIN=1` is set. With the switch off, the CLI returns
  `EXTENSION_DISABLED` and makes no network call. See
  [docs/LIEPIN_INTEGRATION.md](docs/LIEPIN_INTEGRATION.md) (Chinese).

Deleting `careeros/extras/` removes every such integration without touching the rest.

## Repository layout

```text
careeros/            CLI, storage, migrations, deterministic domain logic
careeros/core/       Career Twin Core (assertions, goals, pipeline, signals, context)
careeros/extras/     opt-in third-party integrations (not imported by default)
.agents/skills/      eight career workflows plus document-export
data/examples/       fictional records, safe to publish
docs/                architecture, data model, security, workflows, evaluation
scripts/             demo, smoke test, verification helpers
tests/               core and document-export behavior tests
```

Local private state lives in `data/private/` and `outputs/`; both are Git-ignored.
**Git ignore is not encryption** — enable disk encryption if the machine is shared.

## Security and privacy

`docs/SECURITY.md` (Chinese) is the long version. Short version: job listings, web
pages and inbound messages are untrusted *data*, never instructions; personal data
stays local unless you authorize a specific service, purpose and payload; every
outbound action is user-confirmed.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Most docs are in Chinese; English issues and
pull requests are welcome. Please do not paste real resumes or job databases into
issues — use `data/examples/` or a minimal redacted sample.

## License

MIT © 2026 CareerOS contributors. Job board APIs, data and trademarks belong to
their respective owners; this license grants no rights to those services.
