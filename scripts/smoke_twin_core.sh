#!/usr/bin/env bash
# Optional Bash-only developer smoke; the core workflow does not require Bash.
# For the portable demo, use scripts/demo_hiring_loop.py with a new output directory.
set -u
cd "$(dirname "$0")/.." || exit 1
export ORIWARD_DB="$PWD/outputs/_selftest/e2e.sqlite3"
rm -rf outputs/_selftest && mkdir -p outputs/_selftest
# Python 解释器可用 PYTHON 环境变量覆盖；默认使用 PATH 上的 python
PY="${PYTHON:-python}"
fail=0
check() { if [ "$1" != "$2" ]; then echo "FAIL: $3 (got $1, want $2)"; fail=1; else echo "ok   $3"; fi; }

"$PY" -m oriward init >/dev/null || fail=1

printf '%s' '{"display_name":"示例用户（虚构）","location":"示例城市","values":["自主性","可迁移能力"],"hard_constraints":["不接受长期出差"]}' > outputs/_selftest/profile.json
printf '%s' '{"event":"校级数据看板项目","context":"3 人小组","actions":["用 Python 清洗 2 万条问卷数据"],"outcomes":["院系统计效率提升"],"evidence":[{"claim":"用 Python 清洗 2 万条问卷数据","source":"用户自述+示例项目仓库","status":"user_confirmed"}],"inferred_skills":[{"name":"数据分析","reason":"独立完成清洗","confidence":"medium"}],"approved_for_resume":true}' > outputs/_selftest/exp.json
printf '%s' '{"title":"数据产品经理","rationale":"技术与业务的接口人","supporting_experience_ids":[1],"gaps":["缺少需求文档作品"],"validation_status":"hypothesis"}' > outputs/_selftest/dir.json
printf '%s' '[{"source":"official","source_id":"A1","title":"数据产品经理","company":"示例公司（虚构）","location":"示例城市","description":"负责指标体系。","url":"https://careers.example.com/jobs/A1"}]' > outputs/_selftest/jobs.json

"$PY" -m oriward profile save --file outputs/_selftest/profile.json >/dev/null
"$PY" -m oriward experience add --file outputs/_selftest/exp.json >/dev/null
"$PY" -m oriward career add --file outputs/_selftest/dir.json >/dev/null
"$PY" -m oriward jobs import --json outputs/_selftest/jobs.json >/dev/null

"$PY" -m oriward twin sync-legacy >/dev/null || fail=1
mapped=$("$PY" -m oriward belief list | "$PY" -c "import json,sys;d=json.load(sys.stdin);print(sum(r['assertion_type'] in ('career_hypothesis','skill_hypothesis') for r in d))")
check "$mapped" "2" "legacy direction and inferred skill are mapped"
again=$("$PY" -m oriward twin sync-legacy | "$PY" -c "import json,sys;print(json.load(sys.stdin)['assertions_created'])")
check "$again" "0" "sync-legacy is idempotent"

"$PY" -m oriward pipeline update --job-id 1 --status shortlisted --reason "方向契合" >/dev/null
stage=$("$PY" -m oriward pipeline show --job-id 1 | "$PY" -c "import json,sys;print(json.load(sys.stdin)['pipeline']['discovery_status'])")
check "$stage" "shortlisted" "shortlist without a resume"

printf '%s' '{"title":"半年内转数据产品","priority":1,"status":"active","target_date":"2026-12-31","owner":"user"}' > outputs/_selftest/goal.json
"$PY" -m oriward goal add --file outputs/_selftest/goal.json >/dev/null
printf '%s' '{"title":"写一份需求文档样例","source_type":"goal","source_id":1,"action_type":"learn","due_at":"2026-10-22T20:00:00+08:00","priority":2,"suggestion_reason":"方向缺口"}' > outputs/_selftest/a1.json
"$PY" -m oriward action propose --file outputs/_selftest/a1.json >/dev/null
top=$("$PY" -m oriward action list | "$PY" -c "import json,sys;print(json.load(sys.stdin)['ranked'][0]['title'])")
check "$top" "写一份需求文档样例" "ranking surfaces the due action first"

printf '%s' '{"target_type":"job","target_id":1,"feedback_type":"not_interested","reason":"需要长期驻场"}' > outputs/_selftest/s1.json
"$PY" -m oriward signal add --file outputs/_selftest/s1.json >/dev/null
scope=$("$PY" -m oriward signal list | "$PY" -c "import json,sys;print(json.load(sys.stdin)[0]['scope'])")
check "$scope" "this_case" "feedback stays case-scoped"

sections=$("$PY" -m oriward context brief --max-chars 2600 | "$PY" -c "import json,sys;d=json.load(sys.stdin);print(','.join(k for k in ('who_am_i','who_could_i_become','where_i_am_now','what_next','why') if k in d))")
check "$sections" "who_am_i,who_could_i_become,where_i_am_now,what_next,why" "brief answers all five questions"

dir_id=$("$PY" -m oriward belief list --type career_hypothesis | "$PY" -c "import json,sys;print(json.load(sys.stdin)[0]['id'])")
printf '{"id":%s,"value":{"direction":"数据运营"},"reason":"收窄方向"}' "$dir_id" > outputs/_selftest/revise.json
superseded=$("$PY" -m oriward belief revise --file outputs/_selftest/revise.json | "$PY" -c "import json,sys;print(json.load(sys.stdin)['supersedes'])")
check "$superseded" "$dir_id" "revise links to the superseded claim"

versions=$("$PY" -m oriward belief history --id "$dir_id" | "$PY" -c "import json,sys;print(len(json.load(sys.stdin)['versions']))")
check "$versions" "2" "history keeps both versions"

"$PY" -m oriward reflection weekly >/dev/null
echo
if [ "$fail" = "0" ]; then echo "SMOKE OK"; else echo "SMOKE FAILED"; exit 1; fi
