# Career hypothesis contract

Required fields: `title` (string), `rationale` (string), `supporting_experience_ids` (array of existing ints), `gaps` (array), `validation_status` (normally `hypothesis`).
Recommended: `transferable_skills`, `entry_route`, `job_search_keywords`, `risks`, `market_sources` each with URL and checked date. Never assign `validated` without external evidence and concrete feasibility.

Example: `data/examples/career.json`.

Use `python -m careeros career add --file data/private/career-review.json`; after that `python -m careeros career list`.
