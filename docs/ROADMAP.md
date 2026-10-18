# Roadmap · 当前能力与后续边界

## 当前版本 v0.2.0 · Career Twin Core

产品从"一组能存数据的技能"升级为"一个持续成长的用户状态中枢 + 八个执行技能"。设计见 [CAREER_TWIN_CORE_ARCHITECTURE.md](CAREER_TWIN_CORE_ARCHITECTURE.md)。

- `schema_migrations` 版本化迁移，升级前自动备份，补列幂等。
- `user_assertions` / `assertion_links`：关于用户的每句话都有来源、置信度、有效期与版本链；推断不能自称已确认。
- `user_feedback`：情境化反馈，`promote` 才升格为长期约束，仍需用户 `confirm`。
- `career_goals` / `job_pipeline` / `next_actions`：目标、机会（投递前）、行动三层分开；单岗强制给出阶段/事件/下一步/截止/阻塞/来源。
- `context brief`：五问摘要（Who am I / Who could I become / Where am I now / What next / Why），有界、可钻取、可追溯。
- `reflection weekly`：只产出待审批提案。
- 投递事件补 `from_status/to_status/human_confirmed`；`applications.status` 退化为投影。
- `twin status/sync-legacy/export`：健康检查与 v0.1 单向投影。

## v0.1.0（已完成基线）

- 8 个项目内 Skills，由 Codex 按意图加载。
- 本地 SQLite 和 Markdown 简历；经历证据、岗位、分析、评审、申请、反馈和版本谱系可审计。
- CSV/JSON 岗位导入；公开 Greenhouse/Lever API 同步；不可变来源快照和 freshness。
- 10 个渠道的能力矩阵（`access`/`supports`/`apply_channel`）；`jobs route` 给出每个渠道从检索到投递的具体步骤，`executed:false` 不等于搜到。
- 企业官网直招渠道 `official`：单页只读，JSON-LD `JobPosting` 优先，解析 JD、发布时间与官方投递入口；拒内网/IP/凭据/非 HTTPS。
- 岗位/投递统一记录：`published_at`、JD、同岗多平台渠道（`vacancy_groups`）、投递渠道、`applied_at`、日程节点（`application_events`）、状态与反馈集中在 `jobs card` / `pipeline`。
- 跨来源候选重复组已交付：保留各 source/snapshot，只做候选归并；重复投递只提示不拦截。
- Codex 语义 JD 分析 + CLI 精确引文、经历 ID、job hash 校验。
- exact resume/JD 的七阶段红/蓝模拟招聘审查，CLI 计算 A–D 或 `NEEDS_EVIDENCE`。
- actual/mock/hypothesis 反馈分流、claim-mapped 改版、真人事实确认、独立复审和 feedback resolution。
- 人工投递、本地状态记录；无自动提交连接器。

当前验收重点是端到端证据完整性和错误拒绝能力，不以“更多岗位”或“更高等级”作为成功指标。

## 近期候选项

1. ~~为现有 additive schema 增加显式 migration 版本号和备份/恢复演练~~（v0.2 已交付；恢复演练仍需一次真实故障注入）。
2. 增强 JSON schema/export，允许在不暴露个人资料的条件下复核分析和评审结构。
3. 在用户授权范围内加入更多官方 job board adapter；每个 adapter 单独验证条款、认证、限流和字段语义。
4. 归并规则支持人工纠错：允许用户把错误合并的组拆开，或把漏合并的多平台来源手动串联。
5. 在本地生成 DOCX/PDF 前建立明确的内容版本与视觉 QA 流程。
6. 以真实、匿名化、用户同意的结果评估七阶段诊断价值，而不是把等级训练成 offer 预测。

## 暂不承诺

- BOSS 直聘等国内平台的登录态实时抓取、反爬绕过或全网覆盖。
- 自主批量投递、招聘方消息、账号登录、CAPTCHA 处理。
- 通过第三方服务自动上传个人数据。
- 根据匿名拒信自动判定因果、自动改申请状态或自动提高 grade。
- 把 A 级包装成录用保证，或把 D 级当作对人的价值判断。
- 在没有新证据时无限红蓝迭代。

## 产品化条件

若扩展为多用户产品，必须先具备身份认证、租户隔离、加密、细粒度授权、保留/删除策略、可信的确认界面和迁移机制。任何外部提交连接器都应把“准备”和“发送”分成不同权限，并产生雇主系统可核查的 receipt；模型指令或一个 CLI flag 不能单独充当同意证明。
