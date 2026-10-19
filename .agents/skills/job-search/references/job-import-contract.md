# Job source import contract

Load for file import, lead promotion or provenance/freshness audit. For channel capabilities use [CHINA_JOB_SOURCES](../../../../docs/CHINA_JOB_SOURCES.md); browser operation uses [browser-search.md](browser-search.md).

## Vacancy files and adapters

CSV headers and JSON object fields require `source,title,company,description`; JSON is a top-level array. Recommended: `source_id,location,url,listed_at,retrieved_at,salary,job_type,availability`. Use `jobs import --csv <file>` or `jobs import --json <file>`; max 10,000 records.

URLs are HTTP(S). Supplied `retrieved_at` is non-future timezone-aware ISO-8601; if omitted, source time stays unknown and local `imported_at` is separate. Older/undated observations cannot overwrite a known newer source retrieval; the whole batch is rejected. `availability:unknown|listed|closed` is not proof the employer accepts applications. Dedupe is by source identity, not cross-board similarity.

`jobs sync --provider greenhouse|lever --board <slug> [--company <name>] [--limit 100]` performs bounded public API reads and imports normalized results. A successful empty response differs from network failure; claim success only with command output.

Use `jobs show --id <id>` for freshness and `jobs snapshots --id <id>` for immutable content versions. Timestamp-only refreshes add no snapshot; content hashes exclude retrieval/import times.

## Search leads

Zhiye search reads the first result page only (`--limit` 1..50). Search/detail caches last 15 minutes/24 hours; `--refresh` bypasses them. `leads fetch` reads the aggregate full JD, not an employer link; availability remains unknown and upstream verification labels stay separate.

`leads import --file <json>` accepts at most 1,000 objects with required `provider,title,url,discovered_at,discovery_method`; optional company/location/summary/query and source verification labels remain observations. `discovered_at` is non-future timezone-aware ISO-8601. Methods:

`web_index|local_public_search|authorized_import|browser_ui|official_api|official_site`

For `browser_ui`, `access_state` must be `visible_preview|full_detail`. Non-official provider URLs must match the declared provider domain without credentials; official leads use the public-HTTPS URL guard. Older observations cannot overwrite newer ones (unless explicitly skipped). URL dedupe does not establish shared employer/vacancy identity.

Leads cannot enter analysis or receive grades. After reading the complete individual JD, `leads promote --id <id> --file <json>` requires `title,company,description,url,retrieved_at,read_method,content_complete:true`. Read methods:

`local_public_page|authorized_page_read|user_copy|browser_ui|official_site_read`

`browser_ui` promotion additionally requires `access_state:full_detail`. The URL must exactly match the specific lead; BOSS/Zhilian listing pages are refused. Login-gated previews, snippets and missing requirements cannot be promoted by setting complete flags or inventing content.

`jobs search-plan` and unsupported local routes return `executed:false`; this does not mean no jobs. Never claim an authenticated connector, bypass controls or upload personal data while collecting vacancies.
