# 决策依据与后续结果

Agent 阅读资料并判断语义，Core 校验引用、保存当时状态、检查变化和整理待办。排序分数只表示日程优先级，不代表岗位适合度或成功率。

在推荐岗位/方向、选择投入方案或重评受证据变化影响的建议时使用本契约。普通记账或日程 action 不必逐个填写六因素；未记录适配判断的 action 保持 unassessed。存储实体与输入示例的维护分工见 [DATA_MODEL](DATA_MODEL.md)，操作入口见 [WORKFLOWS](WORKFLOWS.md)。

## 一次建议如何保存

1. 先读取 `context brief`，按需查看完整的 `belief list`、`goal list`、岗位和经历。含糊自述以 `confidence: low` 保存，并把原话、当时约束和待确认问题留在 value/explanation；不要将“可能喜欢”写成已知能力。
2. 使用 `action propose` 保存具体行动及 `suggestion_reason`。有对应对象时填写真实的 source_type/source_id，支持 goal、job、application、learning、interview；不要编造引用 ID。
3. 使用 `python -m careeros decision record --file <reviewed-decision.json>` 保存下面的六类判断。Core 要求每类都有 status/reason，即使答案是 unknown 或 not_applicable。未知事项应生成一个能澄清它的独立调查/确认行动，不要把待验证的申请建议说成已适配。
4. 每个当前有效、非含糊的用户硬约束都必须单独出现在 constraint_checks，注明 satisfied/conflict/unknown、断言 ID 及理由。conflict 的建议不会进入可推荐列表，unknown 进入待核实列表。用户可以讨论、修改、撤回这些判断。
5. 只有用户当下明确接受或否决时，才记录 accepted/rejected 并带 human-confirmed；它不授权任何外部操作。行动完成仍需实际证据或用户确认，Core 会自动把完成事件连接到当前决定。

```json
{
  "action_id": 1,
  "reason": "课程 SQL 项目与岗位清洗任务相符，先用一小时整理案例验证方向",
  "alternatives": [{"title": "先做完整作品集", "reason": "投入更大，先验证岗位是否值得继续"}],
  "factors": {
    "goal": {"status": "supports", "reason": "服务用户确认的数据分析探索目标"},
    "preference": {"status": "supports", "reason": "用户偏好可积累作品的任务", "assertion_ids": [2]},
    "job": {"status": "supports", "reason": "已检查真实岗位当前 JD 和来源日期"},
    "deadline": {"status": "not_applicable", "reason": "此次内部准备无硬截止，岗位投递期限待查"},
    "capability": {"status": "supports", "reason": "用户已确认 SQL 课程项目的具体动作", "experience_ids": [1]},
    "cost": {"status": "supports", "reason": "本周两小时预算内安排一小时", "planned_weekly_hours": 1}
  },
  "constraint_checks": [
    {"assertion_id": 3, "status": "satisfied", "reason": "岗位原文明确无需长期出差"}
  ]
}
```

以上 ID 仅为格式示意，必须替换成当前库的真实记录。factors 必须恰好包含 goal/preference/job/deadline/capability/cost；status 是 supports/conflicts/unknown/not_applicable。能力标为 supports 必须引用已确认且仍有效的能力断言，或带已核实证据、获准使用的经历。推断只能作为 unknown 的待验证线索。

Core 不会从一句“不接受出差”自动猜测所有 JD；Agent 必须逐项读原文并保存核实结果。没有决策记录的旧任务只属于日程排序，assessment=unassessed，不能据此声称“已证实适合”。当关联岗位存在用户硬约束而没有核实记录时，Core 会将推进任务留在 review。

## 查看变化、选择与结果

```text
python -m careeros decision show --id <decision-id>
python -m careeros decision history --action-id <action-id>
python -m careeros decision outcome --id <decision-id> --kind accepted --note "用户明确选择及其理由" --human-confirmed
python -m careeros decision outcome --id <decision-id> --kind rejected --note "用户否决及当时约束" --human-confirmed
python -m careeros decision outcome --id <decision-id> --kind result --note "实际发生的结果" --evidence "本地证据路径或来源"
```

决定冻结当时的用户断言、目标、岗位内容/来源快照、行动定义、证据记录和备选方案。目标、约束、能力或 JD 发生变化后，旧记录保留，当前建议进入重新评估；重新 record 会形成 previous_id 链。保存 accepted 只记录选择，不会把未知能力变成已确认，也不会自动投递。

工时区分总投入与每周安排：action.effort_hours 是任务总量，cost.planned_weekly_hours 是当前方案的每周安排；超过关联用户目标的 time_budget_hours 时应拆分任务或调整规划。Core 不负责自动求解多任务排程，Agent 必须检查整个阶段的总负荷。

## 修改目标和用户认识

```text
python -m careeros goal update --id <goal-id> --status paused --note "期末考试，暂时保留方向但暂停执行"
python -m careeros goal update --id <goal-id> --file <reviewed-update.json>
python -m careeros goal history --id <goal-id>
```

目标更新 JSON 支持 title、direction_id、priority、status、target_date、success_criteria、time_budget_hours、rationale、note；note 必填。每版保存完整前后信息，升级前更早的历史不会被编造。time_budget_hours 可用 null 清除，0 表示当前没有可用工时。

`belief revise` 默认继承来源链接；links 数组显式替换来源，links=[] 显式清除。每版历史保留来源、解释和审计。`profile save` 是兼容入口，身份改动进入同一账本；长期列表只可追加，纠正和撤回使用 belief。旧缓存不能覆盖新纠正，也不能复活撤回的记录。

document-export 仍只转换已准备的内容，不记录决定、不确认事实、不产生职业反馈。
