# CareerOS · evidence-backed career workbench (v0.2.0)

[中文 README](README.md) · [MIT License](LICENSE)

CareerOS is a local-first workbench for one job search at a time. It keeps the
*semantic* work — reading a JD, mapping your real experience to it, arguing with
your own resume — with an agent, and keeps everything that must be reproducible
(versions, provenance, state) in a deterministic Python CLI over SQLite.

Eight skills wrap one loop: discovery → mapping → sourcing → JD analysis →
evidence-locked resume → simulated hiring review → feedback → next action.

**No third-party runtime dependencies.** Python 3.10+ and the standard library.

## This project will not apply to jobs for you

Mass applying has negative expected value. Sending the same resume to dozens of
mismatched postings burns your time, the recruiter's attention, and your standing
with whatever triage system sees you next.

So CareerOS is a *desk before the application*, not an application bot. It does the
things that actually raise the expected value of a single application: decomposing
requirements, aligning evidence, freezing resume versions, recording real feedback.
The submit click stays with you, on the employer's own page.

Deliberately absent: no submit API, no browser auto-clicking, no CAPTCHA bypass,
no credential storage for job boards, no bulk-apply queue. That is a design
decision, not a backlog item.

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

```powershell
python -m pip install -e .          # optional; otherwise prefix commands with python -m

python -m careeros init             # create/migrate the local SQLite schema
python -m careeros twin status      # health check and suggested next step
python -m careeros context brief    # bounded five-question summary
python -m unittest discover -s tests -v

# fictional demo records, safe to use
python -m careeros jobs import --csv data/examples/jobs.csv
python -m careeros jobs card --id 1
```

A full fictional end-to-end run (isolated database, no network, no submissions):

```powershell
python scripts/demo_hiring_loop.py --output outputs/hiring-loop-demo-local
```

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
.agents/skills/      eight orchestration skills
data/examples/       fictional records, safe to publish
docs/                architecture, data model, security, workflows, evaluation
scripts/             demo, smoke test, verification helpers
tests/               132 unit tests
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
