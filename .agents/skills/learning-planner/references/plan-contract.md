# Learning plan JSON

Required: `target_role` string, `gaps` array, `milestones` array, `review_date` ISO date.
Recommended: `job_ids` array of existing IDs, `constraints`, `weekly_hours`, `success_metric`, `status` (`active` initially).

Each milestone should include `title`, `deliverable`, `acceptance_criteria`, optional `due_date` and `resource_urls`.

`python -m careeros learning save --file data/private/plan.json`
`python -m careeros learning list`

Example: `data/examples/learning.json`.
