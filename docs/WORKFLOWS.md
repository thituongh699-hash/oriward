# End-to-end workflows

所有命令从项目根目录运行。Codex 在每个实质步骤后应报告：已验证事实、推断、来源与日期、生成 ID/路径、未知项，以及仍需本人确认的动作。

## 1. 建立证据库

使用 `$career-discovery` 访谈；一次问 2–4 个问题，把事实、证据、推断和未知分开。本人确认事实措辞后：

```powershell
python -m careeros profile save --file data/private/profile.json
python -m careeros experience add --file data/private/experience.json
python -m careeros experience list
```

`approved_for_resume=true` 只来自本人直接确认，不能从“听起来合理”推断。

## 2. 建立方向并取得真实岗位样本

用 `$career-mapping` 把 experience ID 映射到相邻、跨行业和交叉方向；未有招聘证据时标为 hypothesis。岗位有三条入口：

```powershell
python -m careeros jobs import --csv data/private/jobs.csv
python -m careeros jobs import --json data/private/jobs.json
python -m careeros jobs sync --provider greenhouse --board acme --company "Acme" --limit 100
python -m careeros jobs sync --provider lever --board acme --company "Acme" --limit 100
```

Greenhouse/Lever 同步会实际调用其公开 API。国内平台只使用用户授权读取或导出的 JSON/CSV；不得声称存在 BOSS 直聘登录抓取。先看渠道能力再决定走哪条路：

```powershell
python -m careeros jobs channels
python -m careeros jobs route --provider official --query "产品经理" --location "上海"
python -m careeros jobs search --provider zhiye --query "产品经理" --location "上海" --limit 10
python -m careeros jobs search-plan --query "产品经理" --location "上海"
```

官网直招渠道需要单岗 URL，读完即入岗位库（含 JSON-LD 的发布时间与投递入口）：

```powershell
python -m careeros official plan --company "示例科技" --query "产品经理"
python -m careeros official fetch --url "https://careers.example.com/jobs/123" --company "示例科技"
```

导入后检查：

```powershell
python -m careeros jobs list
python -m careeros jobs show --id 1
python -m careeros jobs card --id 1
python -m careeros jobs snapshots --id 1
```

保留精确 URL、retrieved_at 和 availability。手工导入没有来源时间时保持 freshness unknown，并记录本地 imported_at；不要用旧或无日期记录覆盖已有的新观察。fresh/listed 不是仍可申请的绝对证明。

## 3. Codex 语义 JD 分析

```powershell
python -m careeros analysis draft --job-id 1
python -m careeros analysis packet --job-id 1
```

draft 只帮助起步；它按行产生候选要求，所有匹配均为 unknown。Codex 必须阅读完整 JD 和 packet：

1. 合并或拆分语义要求，分类为 `hard_gate|core|preferred`。
2. 每条保存当前 JD 的精确 quote。
3. 只把经批准且有证据的 experience ID 标为 met；没有证据时用 gap 或 unknown。
4. 对目标公司建立 dossier：每项明确 `fact`、`inference`、URL、retrieved_at、availability。
5. 只有确认覆盖完整 JD 后设 `coverage_confirmed=true`。

随后保存：

```powershell
python -m careeros analysis save --file data/private/analysis-1.json
python -m careeros analysis packet --job-id 1
```

若 hard gate 未知，先取证；不要为了输出等级把 unknown 改成 met/gap。

## 4. 简历基线与红/蓝协议

```powershell
python -m careeros resume build --job-id 1 --experience-ids 1,2 --headline "目标岗位"
python -m careeros review packet --resume-id 1
```

### 红方

只审 packet 中冻结的 exact resume/JD/analysis，并覆盖七阶段：

- `ats`：结构、可解析性、关键词证据和硬门槛。
- `hr`：基本匹配、动机、履历解释和沟通风险。
- `hiring_manager`：职责所有权、影响、判断和岗位相关性。
- `technical`：专业深度、方法、工具、边界和可复核成果。
- `pressure`：岗位相关的追问与反证；保持尊重，不问受保护特征，不设计羞辱性或歧视性压力。
- `background`：一致性、可核查性和公开信息风险，不做未经授权的隐私调查。
- `competition`：对公开岗位要求和合理市场基准做假设比较，不编造“其他申请者”。

每个 finding 必须引用观察证据、要求 ID 和 severity。不能在同一份评审里把刚发现的问题写成 resolved。

### 蓝方

对每个 finding 给出一条具体 action：

- `wording`：仅改善已有事实的表达；
- `practice`：准备回答、案例或演练；
- `evidence`：补项目、证照或可核查材料；
- `retarget`：换岗位层级、方向或雇主。

结构性/硬门槛问题不能分配成“润色即可”。保存时让 CLI 计算结果：

```powershell
python -m careeros review save --file data/private/review-1.json
python -m careeros review list --resume-id 1
```

## 5. 改版、确认与独立复审

把 finding 映射到新版本 JSON，每条 bullet 保留同一经历的原始 `source_texts`：

```powershell
python -m careeros resume revise --file data/private/revision-1.json
python -m careeros resume history --id 2
```

若返回 `factual_status=pending`，先把完整改写内容交给本人核实。只有本人明确确认“新的措辞仍准确”后运行：

```powershell
python -m careeros resume confirm --id 2 --human-confirmed
```

然后不要复制旧评审；重新取 packet 独立审查 exact new resume：

```powershell
python -m careeros review packet --resume-id 2
python -m careeros review save --file data/private/review-2.json
```

只有新增证据、实际改版或目标变化才开启下一轮。没有新证据时最多两轮；保留剩余风险并停止文字循环。

## 6. 人工投递与精确版本绑定

```powershell
python -m careeros application prepare --job-id 1 --resume-id 2 --channel boss --apply-url "https://www.zhipin.com/job_detail/xxx.html"
python -m careeros application channel --id 1 --channel official
python -m careeros application event --id 1 --kind interview --label "一面（业务面）" --scheduled-at "2026-10-22T14:00:00+08:00"
python -m careeros application timeline --id 1
python -m careeros application agenda --days 30
```

`prepare` 会返回 `repeat_application_hints`：同一候选岗位组里若已有投递，只做提示，不拦截。`--channel` 记录实际投递渠道，`--apply-url` 记录投递所指向的精确页面。检查岗位 URL、联系人信息、回答和 exact resume ID。用户自行在官方系统提交。用户明确报告“这个版本已经提交成功”后才运行：

```powershell
python -m careeros application record --id 1 --status SUBMITTED --human-confirmed --note "User confirmed actual submission"
```

该命令只是本地记账，会自动写入 `applied_at` 和一条 `applied` 时间线节点。不得自动登录、最终点击、发信或上传个人资料。

## 7. 反馈闭环

把每条信息先分流：

- `actual`：来自真实招聘流程，必须绑定 application 和当时 resume；
- `mock`：模拟面试或人工演练；
- `hypothesis`：基于结果提出、尚未证实的解释。

```powershell
python -m careeros feedback save --file data/private/feedback-1.json
python -m careeros feedback list --job-id 1
python -m careeros feedback plan --job-id 1
```

反馈保存不会改变 application 状态，也不会提高 grade。按 plan 做 wording/practice/evidence/retarget；若产生简历改版，重复“改版 -> 本人确认 -> 独立复审”。完成后：

```powershell
python -m careeros feedback resolve --id 1 --review-id 2 --note "已完成有谱系的改版与复审"
```

resolve 要求新 review 属于链接了该反馈的 revision，且改写事实已确认。

## 8. 学习与面试

把 analysis/review 中的结构性缺口交给 `$learning-planner`，用可验收作品或证据关闭，不把课程完成等同于能力。把 practice actions 交给 `$interview-coach`；模拟回答只保存用户实际说出的内容，company dossier 继续保留来源和日期。

## 9. 统一记录与重复投递判断

一个岗位的全部事实收在一处：发布时间、JD、各平台渠道、投递状态、日程节点、后续反馈。

```powershell
python -m careeros jobs card --id 1
python -m careeros jobs group --limit 50
python -m careeros pipeline
```

- `jobs card`：单岗档案，含 `channels`（同岗在各平台的招聘来源）、`applications`（渠道/状态/`applied_at`/时间线）、`feedback`、`gaps` 和 `next_commands`。
- `jobs group`：同公司同岗位在不同平台出现的归并结果。归并只是候选提示，不证明是同一岗位。
- `pipeline`：漏斗计数、同岗多渠道清单、`repeat_application_risk`、日程、数据缺口。

是否重复投递由用户判断：系统只报告 `already_applied_in_group`，不拦截、不自动去重、不自动合并申请。详见 [APPLICATION_TRACKING.md](APPLICATION_TRACKING.md)。
