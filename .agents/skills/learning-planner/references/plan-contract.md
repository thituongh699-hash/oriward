# Learning plan input

Required: `target_role` string, `gaps` array, `milestones` array, `review_date` ISO date. Recommended: existing `job_ids`, `constraints`, `weekly_hours`, `success_metric`, `status` (initially `active`).

Milestones include title, deliverable, acceptance criteria, optional due date/resource URLs; save using the example keys in `data/examples/learning.json` (`due_date`, `resource_urls`).

Run `learning save --file <private-json>` and inspect `learning list`; record actual work and outputs without inventing mastery. Existing clear self-reports can support resume wording immediately; no resume approval stage is added.
