# Interview session and feedback contracts

Interview session JSON requires `job_id`, `questions`, `practice`, `next_actions`. Recommended: `resume_id`, interview round/date and `company_sources`, where each item preserves URL, retrieved_at, sourced fact and separate inference. Each practice item stores the actual question, user's actual answer, feedback and supporting experience IDs. Never save an invented polished answer as the user's response.

```powershell
python -m careeros interview save --file data/private/interview-session.json
python -m careeros interview list
```

To feed the hiring loop, feedback JSON requires `job_id`, exact `resume_id`, `kind=actual|mock|hypothesis`, one of the seven stage names, `outcome=pass|reject|pending|withdrawn|unknown`, observation, source, non-future timezone-aware observed_at, and at least one categorized action (`wording|practice|evidence|retarget`).

Actual employer feedback additionally requires the matching non-READY application ID. Mock practice uses `kind=mock`; an explanation inferred from silence/rejection uses `kind=hypothesis`. Feedback never changes application status or grade automatically.
