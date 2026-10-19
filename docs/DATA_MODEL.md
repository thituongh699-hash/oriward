# Data model and contracts

SQLite 由 `python -m careeros init` 初始化；默认数据库为 `data/private/careeros.sqlite3`，可用 `CAREEROS_DB` 指定。本文维护实体、不变量和完整输入示例；执行顺序见 [WORKFLOWS](WORKFLOWS.md)，技能 references 维护各任务的操作要求。所有 ID、引文和哈希必须换成当前记录的真实值；示例不是可直接导入的用户数据。私人 JSON/CSV 放在 `data/private/`，简历文件放在 `outputs/resumes/`。

## 核心实体

| 实体 | 关键关系 | 不变量 |
| --- | --- | --- |
| `experiences` | 经历、证据、推断 | 进入简历须 `approved_for_resume=true` 且有已确认/文档验证证据 |
| `jobs` | 当前规范化岗位 | `source_key` 只保证同来源身份；当前行可被新快照刷新 |
| `job_source_snapshots` | job 的历史内容 | 内容变更才新增，数据库触发器禁止更新/删除 |
| `job_analyses` | job 的要求映射 | 要求保留 JD 精确引文和稳定 `job_sha256` |
| `resumes` | job + experience IDs + 文件 | SHA-256 绑定精确本地文件 |
| `hiring_reviews` | resume + analysis | 七阶段完整覆盖；等级由 CLI 计算，不接受输入等级 |
| `resume_versions` | revision -> base | 保存 claim map、反馈/评审来源与事实确认状态 |
| `applications` | job + exact resume | 准备不等于提交；`SUBMITTED` 需真人确认 |
| `application_events` | application 的时间线 | 状态流转自动写入；手工节点可带未来 `scheduled_at` 作为日程 |
| `vacancy_groups` | 归一化公司+岗位+城市 | 一个 `group_key` 一组；只做候选归并，不证明同一岗位 |
| `job_group_members` | job → group | 一个岗位只属于一组；不合并原始 job 与快照 |
| `recruiting_feedback` | job + exact resume + optional application | actual 必须绑定已提交 application；不自动改申请状态 |

## 岗位导入

CSV 和 JSON 记录都要求 `source`、`title`、`company`、`description`。建议字段：`source_id`、`location`、`url`、`published_at`（雇主发布时间）、`listed_at`、`retrieved_at`、`salary`、`job_type`、`availability`。

JSON 顶层可以是记录数组。URL 只能是 HTTP(S)；提供 `retrieved_at` 时，它必须是带时区且不在未来的 ISO-8601 时间；`availability` 为 `unknown|listed|closed`。手工导入省略 `retrieved_at` 时数据库保持 `null`（快照内部为空字符串），freshness 为 unknown，并另存本地 `imported_at`。若同一 source key 已有较新的已知来源时间，较旧或无日期观察会被整个事务拒绝，包括内容相同的 duplicate，防止 freshness 回退。内容哈希排除 `retrieved_at` 和 `imported_at`。单次导入最多 10,000 条。`source_key = source + (source_id else canonical URL else title/company/location hash)`，不代表跨来源语义去重。

Greenhouse/Lever adapter 还会保留 provider 字段和原始 HTML，同时把 `description` 规范化为纯文本。`jobs show` 返回 freshness：`fresh|stale|unknown` 只衡量抓取时间；`listed` 也只是来源返回状态，不是雇主对申请开放性的保证。

## 岗位统一记录

`published_at` 表示雇主发布时间，与 `retrieved_at`（本地读取时间）是两个字段；只接受 ISO 日期（`YYYY-MM-DD`）或带时区的 ISO 时间戳，缺失保持 `null` 而不是回填抓取时间。`jobs card` 会给出 `published_at_source`，说明取的是 `published_at` 还是回退到 `listed_at`。

`jobs card` 是单岗唯一记录：`job`（标题/公司/城市/发布时间/可用性/freshness）、`jd`（全文与字数）、`vacancy_group`（归并组与成员数）、`channels`（各平台来源）、`applications`（渠道/状态/`applied_at`/时间线）、`feedback`、`repeat_application_risk`、`gaps`、`next_commands`。

跨平台归并键为 `sha256("\u001f".join([normalize(company), normalize(title), normalize(location)]).encode("utf-8")).hexdigest()[:24]`，三个归一化字段以 U+001F 分隔。公司去常见公司后缀及括号噪声；岗位去括号噪声和结尾招聘词；城市取首个城市词并去行政后缀。跨城市不归并，同组仍可能是不同职级、团队或批次，只作候选提示。归并按需重建，`jobs group --rebuild` 可强制重算；原始 `jobs`、`source_key` 和快照均保留。

`application prepare` 返回 `repeat_application_hints` 和 `already_applied_in_group`；卡片的 `repeat_application_risk.decision=user_decides`。不阻止同组再次准备、不合并申请、不把同组全标为已投递，岗位关闭也不删除历史。`jobs card.gaps` / `pipeline.data_gaps` 报告缺失发布时间、JD、申请渠道或投递 URL，不猜测补齐。聚合渠道的 availability 保持 unknown，不能用聚合抓取时间证明雇主仍开放。

`applications` 的 `channel` 只接受渠道 ID 或 `email|referral|other`；`apply_url` 记录实际提交页面；`applied_at` 仅在 `SUBMITTED` 且本人确认后写入。`application_events` 由状态流转自动追加，也可用 `application event` 写入未来日程。

## 结构化分析 JSON

先用 `analysis draft` 获取模板，再由 Agent 根据 `analysis packet` 完整填写：

```json
{
  "job_id": 1,
  "coverage_confirmed": true,
  "requirements": [
    {
      "id": "req-license",
      "text": "具备所需执照",
      "kind": "hard_gate",
      "quote": "必须持有……执照",
      "match": "met",
      "experience_ids": [4],
      "rationale": "经历 4 的已确认材料直接证明"
    }
  ],
  "unknowns": [],
  "company_context": [
    {
      "url": "https://company.example/careers/1",
      "retrieved_at": "2026-10-18T09:00:00+08:00",
      "fact": "官方职位页仍列出该岗位",
      "inference": "团队可能重视跨部门协作",
      "availability": "listed"
    }
  ]
}
```

规则：

- `quote` 必须是当前 JD 的精确子串；不要改写后冒充原文。
- `kind` 为 `hard_gate|core|preferred`；`match` 为 `met|gap|unknown`。
- 只有 `met` 可带 `experience_ids`，且每个经历必须获准进入简历并有非空的 `user_confirmed|document_verified` 证据。
- `coverage_confirmed=true` 只表示 Agent 已检查完整 JD 并确认 requirements 覆盖完整，不表示候选人匹配。
- `company_context` 每项都把可核查事实和推断分开，并保留 URL、日期和 availability。
- recommendation/confidence 由保存逻辑计算；输入中的同名结论不是权威。

## 七阶段评审 JSON

`review packet` 提供模板。若还没有结构化分析，模板中的 `analysis_id` 可以为 `null`；此时先完成分析，不能保存正式评审。

```json
{
  "resume_id": 2,
  "analysis_id": 3,
  "resume_sha256": "<packet value>",
  "stages": {
    "ats": {"verdict": "pass", "rationale": "...", "questions": [], "requirement_ids": ["req-license"]},
    "hr": {"verdict": "pass", "rationale": "...", "questions": [], "requirement_ids": []},
    "hiring_manager": {"verdict": "risk", "rationale": "...", "questions": ["..."], "requirement_ids": []},
    "technical": {"verdict": "pass", "rationale": "...", "questions": [], "requirement_ids": []},
    "pressure": {"verdict": "pass", "rationale": "...", "questions": [], "requirement_ids": []},
    "background": {"verdict": "pass", "rationale": "...", "questions": [], "requirement_ids": []},
    "competition": {"verdict": "risk", "rationale": "...", "questions": [], "requirement_ids": []}
  },
  "red_findings": [
    {
      "id": "f-1",
      "stage": "hiring_manager",
      "severity": "preparation",
      "issue": "所有权表述不清",
      "evidence": "简历只写了团队完成",
      "requirement_ids": [],
      "resolved": false
    }
  ],
  "blue_actions": [
    {"finding_id": "f-1", "action": "准备本人职责和取舍的回答", "type": "practice"}
  ],
  "company_mismatch": {"demonstrated": false, "evidence": ""},
  "result_label": "SIMULATED_HIRING_REVIEW_NOT_EMPLOYER_VERDICT"
}
```

`verdict` 为 `pass|risk|fail|unknown`，每个 requirement ID 至少被某一阶段覆盖；finding severity 为 `presentation|preparation|structural|blocker`；action type 为 `wording|practice|evidence|retarget`。同一评审中的 finding 不能写 `resolved=true`，结构性问题不能只分配 wording。具体评审步骤见 [analysis-contract](../.agents/skills/job-analysis/references/analysis-contract.md)。

CLI 拒绝输入 `grade/status/reasons`，并校验简历文件哈希、analysis/job 哈希、job/resume 关系及“met 证据已选入该简历”。

## 等级语义

- **A**：`coverage_confirmed=true`，所有要求 met、七阶段全 pass、没有 unknown，且 30 天内的来源仍为 listed；表示强证据匹配，不保证 offer。
- **B**：ATS/HR 预期通过但有准备风险，或完整覆盖/当前来源等 A 条件未满足；可能为 provisional。
- **C**：筛选仍有可能，但有 core/preferred 实质差距、竞争劣势、非门槛阶段失败或结构性 finding。
- **D**：已知 hard gate gap、ATS/HR/background fail、关闭岗位、已证实公司不匹配或 blocker。
- **NEEDS_EVIDENCE**：无法诚实给等级，例如未知硬门槛、ATS/HR 尚不能判 pass、改写事实待确认。已知 D 级原因优先于 unknown gate。

开放状态必须来自该岗位本身的当前记录，或与该岗位 URL 对应的有日期来源；公司新闻页或其他职位不能替代目标职位证据。当前岗位为 closed 时优先返回 D，分析建议 skip，不能用 dossier 中的 listed 覆盖。旧评审或待补证据的评审不能用于关闭反馈。

## 反馈 JSON

```json
{
  "job_id": 1,
  "resume_id": 2,
  "application_id": 1,
  "kind": "actual",
  "stage": "hr",
  "outcome": "reject",
  "observation": "招聘方邮件表示经验年限不足",
  "source": "用户查看的招聘方邮件",
  "observed_at": "2026-10-18T10:00:00+08:00",
  "actions": [
    {"category": "retarget", "text": "筛选更匹配当前年限的岗位"}
  ]
}
```

`kind=actual|mock|hypothesis`；`stage` 使用七阶段名；`outcome=pass|reject|pending|withdrawn|unknown`；action category 为 `wording|practice|evidence|retarget`。`actual` 必须有 application ID，且 application 不能仍是 `READY_FOR_USER`，job/resume/application 必须完全一致。拒绝原因仍是一次观察，不自动证明普遍因果。

## 改版 JSON

```json
{
  "base_resume_id": 2,
  "review_id": 5,
  "feedback_ids": [1],
  "reason": "回应 f-1 并保持事实边界",
  "sections": [
    {
      "experience_id": 4,
      "bullets": [
        {
          "text": "协调三方完成交付",
          "source_texts": ["协调三方", "完成交付"]
        }
      ]
    }
  ]
}
```

每个 `source_texts` 必须逐字存在于同一经历的 action、outcome 或 evidence claim。重写后的 `text` 只要不是原事实逐字复用，就标为 pending，必须由用户核实完整表述后确认；操作见 [resume-review](../.agents/skills/resume-builder/references/resume-review.md)。

## 申请状态

```text
READY_FOR_USER -> SUBMITTED -> INTERVIEW -> OFFER -> ACCEPTED
       |              |             |          \-> DECLINED
       |              |             \-> REJECTED/WITHDRAWN
       |              \-> REJECTED/WITHDRAWN
       \-> WITHDRAWN
```

`SUBMITTED` 只记录用户明确报告的真实提交。它不是提交 API，也不会上传文件。

`application_events` 的每次状态流转额外记录 `from_status`、`to_status`、`human_confirmed` 与 `evidence_ref`，使 `applications.status` 成为可由事件重建的投影。

## Career Twin Core

当前 schema v4。结构变更由 `careeros/migrations.py` 的 `MIGRATIONS` 序列管理，记录于 `schema_migrations`；首次升级非空库前写出 `careeros.sqlite3.bak-v<旧版本>-<时间戳>`。

| 表 | 关键字段 | 不变量 |
| --- | --- | --- |
| `user_assertions` | `subject/predicate/value_json`、`assertion_type`、`epistemic_status`、`confidence`、`source_type/source_ref`、`supersedes_id/superseded_by_id`、`valid_from/valid_to`、`dedupe_key` | 不原地修改；改动必须新版本并闭合旧行；`inferred` 不得自称 `user_confirmed` |
| `assertion_links` | `assertion_id`、`ref_type`、`ref_id`、`relation` | `relation ∈ supports/contradicts/derived_from/about`；Why 维度只认这些边 |
| `user_feedback` | `target_type/target_id`、`feedback_type`、`reason`、`scope`、`promoted_assertion_id` | 默认 `scope=this_case`；`promote --human-confirmed` 才升格为长期约束 |
| `career_goals` | `title`、`direction_id`、`priority(1..5)`、`status`、`target_date`、`success_criteria_json`、`time_budget_hours`、`owner(user|agent)`、`rationale` | 仅 user 所有的 active/exploring 目标驱动优先级；每周预算为 null 或 0..168，0 表示无工时 |
| `job_pipeline` | `job_id`(PK)、`discovery_status`、`goal_id`、`decision_reason`、`priority`、`last_checked_at`、`next_review_at` | 与 `applications` 分离：无简历也能进短名单；状态转换受白名单限制；`goal_id` 让岗位归到目标 |
| `next_actions` | `title`、`source_type/source_id`、`action_type`、`status`、`due_at`、`priority`、`effort_hours`、`depends_on_json`、`suggestion_reason`、`requires_approval` | 必须有 `suggestion_reason`；完成需证据或用户确认；`effort_hours` 参与投入成本排序 |
| `reflection_runs` | `period_start/period_end`、`input_event_ids_json`、`proposed_updates_json`、`status` | 只生成提案，不自动改写画像 |

断言类型：`fact / preference / value / constraint / skill_hypothesis / career_hypothesis`。认识状态：`user_stated / user_confirmed / document_verified / inferred / disputed / retracted`。`constraint` 是本项目的落地扩展，用于硬约束过滤。

身份读取使用 Core 投影：兼容 profile 缓存加有效断言，断言中的纠正优先。`profile save` 与断言同事务提交，长期列表只追加；纠正/撤回使用 belief，旧缓存或 `twin sync-legacy` 不得覆盖新纠正、复活撤回。同步对旧 profile、方向、经历能力推断和岗位作幂等单向投影，保留历史映射，不改原文档。

`belief revise` 默认继承证据链接；显式 links 替换，`links=[]` 清除，每版保留自己的来源与解释。来源决定初始认识状态：user_message/interview/legacy_profile/feedback → user_stated；document → document_verified；experience → user_confirmed；model_inference/reflection/external_source → inferred。后三类只能提出 inferred，不能覆盖成用户自述或已确认事实。来源必须真实，状态默认值不等于可伪造证据或代用户确认。

`belief propose` 的能力推断输入示例（经历 3 须真实存在）：

```json
{
  "subject": "skill:sql",
  "predicate": "has_skill",
  "value": {"skill": "SQL"},
  "assertion_type": "skill_hypothesis",
  "source_type": "model_inference",
  "confidence": "medium",
  "explanation": "经历 3 中的查询工作提示待验证的 SQL 能力",
  "links": [{"ref_type": "experience", "ref_id": 3, "relation": "derived_from"}]
}
```

`action propose` 的输入示例（目标 1 须真实存在）：

```json
{
  "title": "写一份需求文档样例",
  "source_type": "goal",
  "source_id": 1,
  "action_type": "learn",
  "due_at": "2026-10-22T20:00:00+08:00",
  "priority": 2,
  "effort_hours": 2,
  "suggestion_reason": "方向缺口：缺少需求文档作品"
}
```

action 还可有 `depends_on`（真实 action ID 数组）和 `requires_approval`。source_type 为 goal/job/application/learning/interview/reflection/core；action_type 为 apply/research/prepare/follow_up/practice/learn/decide/confirm/log_result/other；priority 为 1..5，effort_hours 为总投入 0..200。关联通过岗位、申请、学习计划或面试向目标解析，不能编造 ID。行动状态为 todo/doing/blocked/done/cancelled，完成需证据或用户确认。

其他 Core 文件输入：

| 命令 | 输入字段与边界 |
| --- | --- |
| `belief revise` | id、value；可选 confidence/explanation/source_type/source_ref/reason/links |
| `goal add` | title；可选 direction_id/priority/status/target_date/success_criteria/time_budget_hours/owner/rationale；status 为 exploring/active/paused/achieved/discarded，success_criteria 为数组 |
| `signal add` | target_type、target_id、feedback_type；可选 reason/source/scope。target_type 为 career_direction/job/goal/action/plan/brief/resume/system；feedback_type 为 interested/not_interested/applied/declined/corrected/useful/not_useful/accepted/rejected/other；scope 默认 this_case，general 不代替人工批准推广 |

CLI 拒绝未知字段。信号指向存储实体时须有真实记录；升格只接受明确的长期规则，不能只保存“不感兴趣”等泛标签。招聘方反馈与用户偏好信号不可互换。

文档导出不产生数据：只在 `outputs/` 写 DOCX/PDF 与 manifest，不新增或修改任何表。

旧表与 Core 的分工：`experiences`、`jobs`、`job_analyses`、`resumes`、`learning_plans`、`interviews` 保持 JSON 文档形态（整段叙述有意义）；只有需要被单独引用、质疑和追溯时间的判断才拆成原子。`recruiting_feedback`（招聘方反馈）与 `user_feedback`（用户偏好信号）语义不同，不合并。

## 目标历史与决策

- `goal_revisions` 保存 goal_id/revision、完整 snapshot、reason 和创建时间；当前目标保留在 career_goals。升级时只补当前基线，不编造更早历史。
- `decision_records` 保存 action_id/previous_id、reason、alternatives、六类 factors、constraint_checks、冻结 context 和时间；历史记录不可 UPDATE。
- `decision_events` 追加 accepted/rejected/result/completed；接受/否决须当下用户确认，实际结果须确认或证据。
- 决策 context 冻结当时断言及其链接、关联目标、岗位及来源快照、行动定义和引用的经历证据。当前状态变化会使建议要求重评，旧记录保留。
- assessment 为 eligible、unassessed（日程任务，未证实适配）、validation（澄清未知）、review 或 excluded；后两类不会进入可执行推荐列表。
- 具体 JSON、字段准入和命令见 [DECISIONS.md](DECISIONS.md)。
