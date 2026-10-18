# Job source import contract

## Files

CSV requires headers `source,title,company,description`. JSON uses a top-level array of objects with the same required fields. Recommended fields: `source_id,location,url,listed_at,retrieved_at,salary,job_type,availability`.

```text
python -m careeros jobs import --csv data/private/jobs.csv
python -m careeros jobs import --json data/private/jobs.json
```

URLs must be HTTP(S). `retrieved_at`, when supplied, is a non-future ISO-8601 timestamp with timezone. If a manual record omits it, source time remains null/unknown and local `imported_at` is stored separately. An older or undated observation cannot overwrite an existing newer known retrieval for the same source key; the whole batch is rejected. `availability` is `unknown|listed|closed`. Single imports are capped at 10,000 records. The importer deduplicates only within a source identity; it does not assert that similar cross-board postings are the same vacancy.

## Public adapters

```text
python -m careeros jobs sync --provider greenhouse --board <slug> [--company <name>] [--limit 100]
python -m careeros jobs sync --provider lever --board <slug> [--company <name>] [--limit 100]
```

These commands make bounded public API reads and import the returned normalized records. A successful zero-record response is not a network failure. Never claim a sync succeeded without command output.

## Audit

```text
python -m careeros jobs show --id 1
python -m careeros jobs snapshots --id 1
```

`show` includes freshness. A URL, fresh observation or listed status alone does not prove the listing still accepts applications. Content changes add immutable snapshots; a retrieval-time-only refresh does not create a new content version. Content hashes exclude both source retrieval and local import timestamps.

## China search leads

`jobs search --provider zhiye --query "产品经理" --location "上海" --limit 10` executes bounded public HTML search locally (first result page only, limit 1..50). Search cache: 15 minutes; detail cache: 24 hours. `--refresh` bypasses page cache. `leads fetch --id 1` fetches a full aggregate JD. `availability` remains unknown; upstream verification dates are preserved separately. No employer link is fetched automatically.

BOSS/Zhilian public search results can be saved by `leads import --file <json>` as an array:

```json
[{"provider":"zhilian","title":"示例岗位","url":"https://www.zhaopin.com/jobdetail/EXAMPLE.htm","discovered_at":"2026-10-01T00:00:00+00:00","discovery_method":"web_index","company":"示例公司","location":"上海","summary":"索引摘要"}]
```

The example is fictional. Methods: `web_index|local_public_search|authorized_import`. Max 1000 leads; URLs must match the declared provider domain. Leads are not jobs and cannot enter analysis or receive grades. URL deduplication does not merge employers or cross-platform postings.

After reading the complete individual JD, `leads promote --id <id> --file <json>` requires `title,company,description,url,retrieved_at,read_method,content_complete:true`. `read_method` is `local_public_page|authorized_page_read|user_copy`; the URL must exactly match the lead. Missing requirements cannot be filled from snippets. Indexed listing pages on BOSS/Zhilian are refused as individual vacancies.

`jobs search-plan` and unsupported local providers return `executed:false`, never fabricated leads. Do not claim a live authenticated BOSS connector, circumvent controls or upload personal data while collecting jobs.
