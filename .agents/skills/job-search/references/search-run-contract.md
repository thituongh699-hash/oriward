# Search-run receipts

Use this contract for every search attempt. It records local evidence and does not perform searches, enable extensions, authenticate, submit applications or decide candidate fit.

## One route

Integrated `jobs search`, `leads fetch`, `official fetch`, `jobs sync` and `jobs browser-record` commands create a report for the route. The report distinguishes `success`, `failed`, `auth_required`, `not_connected`, `not_attempted` and evidence-backed `zero_results`. Exceptions still produce a failed report; the original exception is returned with the run ID and report path. A search plan is not an executed search.

## Multiple routes

Create one batch before channel work:

```text
python -m oriward search-run start --file <private-json>
```

The JSON contains `scope` and `planned_channels`, plus optional `output_dir`. `scope` may include `query`, `companies`, `roles`, `location`, `cities`, `keywords`, `filters`, `time_window`, `requested_limit`, `board`, `source_url`, `company` and `limit`. Do not copy personal experience details into the scope.

After each route, record a JSON object with `provider`, `status`, optional `attempted`, `reason`, `coverage`, `counts`, `next_action`, `source_url` and `observed_at`:

```text
python -m oriward search-run record --id <run-id> --file <receipt-json>
```

Counts are nonnegative integers or null for unknown: `leads`, `full_jds`, `imported`, `deduplicated`. Unexecuted routes keep counts unknown. A zero-result receipt requires evidence that a search completed and explicitly returned no results. Browser visible counts are leads, not full JDs. Add brief source-linked candidate summaries and finish the batch to refresh its report:

```text
python -m oriward search-run candidates --id <run-id> --file <private-json>
python -m oriward search-run finish --id <run-id>
python -m oriward search-run show --id <run-id>
```

Reports separate source publication/update dates, employer deadline, start date, duration, application URL, retrieval/import times and any suggested preparation date. Missing values remain “未披露”. A successful bounded page or board response describes only its returned coverage; failures are not empty results, and local or cross-channel dedupe does not prove employer/job identity.

Candidate summaries may contain `id`, `lead_id`, `job_id`, `provider`, `source`, `company`, `title`, `location`, `url`, `core_tasks`, `fit_reason`, `uncertainties`, `evidence_level`, `published_at`, `updated_at`, `deadline`, `start_date`, `duration`, `application_url`, `apply_url`, `retrieved_at`, `discovered_at`, `imported_at`, `source_verified_label`, `time_sources`, `availability`, `suggested_apply_date`, `priority_reason` and `next_action`. Excluded fields such as full descriptions and experience-library contents are not copied to reports.
