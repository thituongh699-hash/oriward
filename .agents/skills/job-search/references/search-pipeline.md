# Staged search pipeline

`oriward.search_cli.dispatch` schedules `start`, `next`, `record`, `record-stage` and `finish`; the CLI is the receipt interface. It never operates browsers or creates fictional search results. Every enabled route needs one actual attempt before repairs. Auth waits are recorded for user assistance and do not block other routes. Repair is capped at two attempts per failed route, each with a distinct `repair_action`; then run two distinct expansions (alias/tasks, then industry/scenario/company/tools). Same-day normalized queries reuse prior work unless explicitly refreshed.

Start a batch with a scope and optional output directory:

```json
{"scope":{"query":"数据分析实习","cities":["上海"]},"planned_channels":["zhiye","boss"],"output_dir":"outputs/search"}
```

Use `search-run plan --file <json>`, then `search-run next --id <run-id>`. Record each actual route action in a separate JSON receipt, for example `{"provider":"zhiye","status":"success","attempted":true,"reason":"检索页返回线索","counts":{"leads":8},"query":"数据分析实习"}`. Repair receipts add `"stage":"repair","repair_action":"alternate_public_route"`; expansion receipts add `"stage":"expansion"` and a distinct query. A receipt with `attempted:false` is an auth/unconnected/waiting state, never zero results.

Attempt history is append-only and includes round, query, route, timestamp and actual-execution state. A planned packet is not an attempt. Full-detail freshness targets are 72 hours for JD details, 24 hours for resume candidates and 7 days for company catalogues; store observed/retrieved times and refresh decisions.

Company catalogues target ten sourced companies in the requested cities. Each needs a sourced reason and evidence of local presence, plus a complete/incomplete scan receipt. Each company scan is capped at five pages and 200 items; collect at most five complete JDs per company. Continue with explicit remaining coverage. Titles/snippets are leads; promote only a complete individual JD using [job-import-contract](job-import-contract.md).

Create three to five experience-derived direction hypotheses and validate each against stored complete JD job IDs in the requested cities and current, reviewable experience IDs. Do not mark directions complete from titles, broad sector assumptions or plans. Pipeline finish requires catalogue and direction stages; partial finish requires a recorded reason. Continue from the latest successful search checkpoint; preserve rejected jobs without recommending them again, and refresh candidate details older than 24 hours before tailoring.
