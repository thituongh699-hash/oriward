# Bounded implementation research · 2026-10-18

本轮只调研与岗位来源 adapter、简历版本/反馈闭环直接相关的现有方案。GitHub repository/contents API 与项目原始文件在 2026-10-18 检查；以下区分源码事实、上游自述和 CareerOS 决策，不把上游 README 当成已在本项目部署的能力。

## JobSpy

来源：

- `jobspy/__init__.py` 原始源码：<https://raw.githubusercontent.com/speedyapply/JobSpy/main/jobspy/__init__.py>
- 仓库：<https://github.com/speedyapply/JobSpy>

已验证源码事实：`SCRAPER_MAPPING` 把多个 `Site` 映射到独立 scraper 类；`scrape_jobs` 校验统一 `ScraperInput`，并把各 adapter 返回的 `JobPost` 合并为一致表结构。2026-10-18 GitHub contents API 返回该文件路径和 blob SHA `3821545a887dbfd4d14299eaf78bf53b4ab060e4`。

采用的思路：CareerOS 让 provider adapter 统一映射到小型岗位模型（source/source_id/title/company/location/url/description/retrieved_at），再走同一导入、哈希和快照路径。

没有采用：引入 JobSpy 依赖、复制其站点 scraper、并发抓取多平台或宣称其支持站点在 CareerOS 中可用。当前只实现经过边界约束的 Greenhouse/Lever 官方公开接口。

## Reactive Resume

来源：<https://github.com/reactive-resume/reactive-resume>

上游 README 自述其支持简历/求职信编辑、版本、申请追踪、导入导出、可选 AI 和自托管。GitHub API 显示仓库存在且默认分支为 `main`；这些是上游项目及 README 的状态，不代表 CareerOS 已部署或验证对应功能。

采用的产品概念：文档版本要绑定申请；改动应可审查；申请结果和“发送过哪份文档”需要谱系。

没有采用：其 UI、模板、PDF/Word 导出、账号系统、AI provider、MCP/API、自托管部署和申请面板。CareerOS 当前仍是本地 CLI + Markdown + SQLite，绝不把个人数据自动发送到 Reactive Resume 或其他第三方服务。

## Greenhouse Job Board API

官方文档：<https://docs.greenhouse.io/job-board.html>

CareerOS 使用公开 GET job board 数据的最小子集，并在本地映射字段、清理可读 description、保存原始内容和检索时间。实现只允许 `boards-api.greenhouse.io` 的 HTTPS 请求及同主机重定向，限制响应大小、超时和条数，不使用候选人提交端点。

文档存在不等于任意公司 board slug 有效，也不证明返回岗位仍接受申请。调用结果必须连同 retrieved_at、availability 和快照解释。

## Lever Postings API

官方仓库/文档：<https://github.com/lever/postings-api>

CareerOS 使用公开 JSON postings 的读取模式，映射职位文本、分类、地点、employment type、hosted URL 和来源 ID。2026-10-18 GitHub API 显示官方文档仓库存在，默认分支为 `master`。

当前实现不登录 Lever，不提交申请，不持有凭据，不把个人资料发送到 Lever。读取公开 posting 与确认岗位仍开放是两件事。

## 对 CareerOS 的结论

1. 使用 adapter -> normalized record -> immutable snapshot 的窄接口，保留来源特有原始字段以便审计。
2. CLI 负责确定性导入、哈希和版本；Agent 负责 JD 语义和证据判断。
3. 简历、申请、反馈、评审必须绑定 exact version；改写不能覆盖原版或继承旧等级。
4. 公开 adapter 逐个加入并验证；国内平台当前只接受用户授权读取/导出 JSON/CSV，不声称存在实时 BOSS 授权 scraper。
5. 不因上游 README 宣称某功能就把它列为 CareerOS 已交付；功能和 live 行为必须在本项目测试中单独验证。
