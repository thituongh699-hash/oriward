# CareerOS · Codex-first 求职工作台（v0.2.0 · Career Twin Core）

CareerOS 把求职推理交给 Codex，把可复现的校验、版本和状态交给本地 Python CLI + SQLite。项目内 8 个 Skills 约束从经历发现、岗位采集、JD 分析、红蓝评审、简历改版到真实反馈复盘的流程。

v0.2 的产品核心是 **Career Twin Core**：一个带来源、置信度和版本链的用户状态中枢，向 8 个 Skills 提供统一的读写接口与上下文摘要。它持续回答五个问题——我是谁、我可能成为谁、我现在在哪、下一步做什么、你凭什么这么认为。设计见 [docs/CAREER_TWIN_CORE_ARCHITECTURE.md](docs/CAREER_TWIN_CORE_ARCHITECTURE.md)。

当前版本可以读取公开的 Greenhouse/Lever job board、只读解析企业官网单岗页面（JSON-LD JobPosting 优先）、导入 JSON/CSV、保存不可变岗位快照、把同一岗位在多个平台的来源归并分组、记录发布时间/投递渠道/日程节点与反馈，生成证据约束的 Markdown 简历、冻结具体简历与 JD 版本进行七阶段模拟招聘评审，并追踪改版与反馈。它不会自主调用外部模型、登录招聘账号、代投、联系招聘方或绕过验证码。所谓 A–D 是本地模拟审查结果，不是雇主决定或 offer 概率。

> **这个项目不会替你投简历，因为海投是负期望的。**
>
> 它是一张"投递前的桌面"，不是一台"投递机器"。投递量增加不等于机会增加：同一份简历投向几十个不匹配的岗位，消耗的是你的时间、招聘方的注意力，以及被系统标记为低质量申请的风险。所以这里只做那些真正提升单个投递期望值的事——把岗位要求拆开、把经历证据对齐、把简历版本钉死、把反馈记清楚——最后的提交动作永远由你本人在官方页面完成并确认。
>
> 相应地，系统不保存招聘账号密码、不模拟点击、不绕过验证码、不代发消息，也不提供"一键海投"。这类功能不是没做，是刻意不做。

## 目录

- [快速开始](#快速开始)
- [当前招聘闭环](#当前招聘闭环)
- [八个 Skills](#八个-skills)
- [文档](#文档)
- [本地数据](#本地数据)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

## 快速开始

需要 Python 3.10+，无第三方运行时依赖（只用标准库）。

```powershell
# 可选：安装为命令。不装也能用，所有命令前加 python -m 即可
python -m pip install -e .

python -m careeros init            # 建库/迁移，输出 schema 版本
python -m careeros twin status     # 健康检查与建议下一步
python -m careeros context brief   # 五问摘要（有界、可钻取）
python -m unittest discover -s tests -v
python -m careeros brief           # 旧版计数摘要
```

`init` 会自动创建 `data/private/`（该目录被 Git 忽略）。想先用虚构数据跑通流程，导入仓库内的示例记录：

```powershell
python -m careeros jobs import --csv data/examples/jobs.csv
python -m careeros jobs card --id 1
```

`data/examples/` 下全部为虚构记录，可直接使用；不要把真实简历或岗位库提交进仓库。

要在不碰真实数据库、不开网络、不投递的情况下查看完整 B→A 虚构闭环，请指定一个尚不存在的输出目录：

```powershell
python scripts/demo_hiring_loop.py --output outputs/hiring-loop-demo-local
```

脚本创建隔离 SQLite、原版/修订版简历、18 次独立 CLI 调用记录和 `REPORT.md`。演示的岗位、候选人、反馈和评级全部虚构；它验证工作流接线，不验证真实招聘效果。

在 Codex 中先要求其读取 `AGENTS.md`，再按意图调用项目 Skill，例如：

> 使用 `$job-analysis` 分析岗位 ID 1。先取分析 packet，由你完成语义化 JD 拆解和证据映射；不要把 CLI draft 当作自动评分。

## 当前招聘闭环

```text
公开来源/API 或授权导出 -> 岗位快照 -> Codex 语义分析 -> 证据约束简历
-> 红方七阶段审查 -> 蓝方 finding-to-action -> 改版与真人事实确认
-> 独立复审 -> 人工投递 -> 真实/模拟/假设反馈分流 -> 下一轮行动
```

### 1. 岗位来源与快照

```powershell
python -m careeros jobs import --csv data/private/jobs.csv
python -m careeros jobs import --json data/private/jobs.json
python -m careeros jobs sync --provider greenhouse --board BOARD_SLUG --company "Company" --limit 100
python -m careeros jobs sync --provider lever --board BOARD_SLUG --company "Company" --limit 100
python -m careeros official plan --company "Company" --query "目标岗位"
python -m careeros official fetch --url "https://careers.company.com/jobs/123" --company "Company"
python -m careeros jobs show --id 1
python -m careeros jobs card --id 1
python -m careeros jobs snapshots --id 1
```

`jobs show` 同时给出 freshness；fresh 只说明来源检索时间在阈值内，不保证岗位仍开放。手工导入缺少 `retrieved_at` 时保持 unknown，只另记本地 `imported_at`；较旧或无日期的记录不能覆盖同一 source key 已有的较新观察。Greenhouse/Lever 同步调用公开、只读、固定主机的 HTTPS JSON 接口，不带账号 cookie 或授权头。本项目没有 BOSS 直聘登录态抓取器。

中国职位搜索与本地节省 token 的默认流程：

```powershell
python -m careeros jobs channels
python -m careeros jobs search --provider zhiye --query "产品经理" --location "上海" --limit 5
python -m careeros leads fetch --id 1
python -m careeros jobs shortlist --query "产品 数据" --location "上海" --exclude "外包"
python -m careeros jobs search-plan --query "产品经理" --location "上海" --providers boss,zhilian
python -m careeros --output data/private/analysis-draft.json analysis draft --job-id 1
```

职页本地搜索只保存线索，完整 JD 获取后进入岗位库；BOSS/智联计划需配合实际公开检索或授权导入，`executed:false` 不代表搜索成功。搜索/详情缓存和本地筛选不调用模型。`--output` 将完整 JSON 写入文件，只输出路径/大小/hash；该参数须放在 domain 前。分析和评审 packet 推荐添加 `--compact`，完整 JD、简历和证据仍保留。详见 [中国渠道](docs/CHINA_JOB_SOURCES.md) 和 [本地执行](docs/LOCAL_EXECUTION.md)。

猎聘渠道以**可选扩展**形式提供（`careeros/extras/liepin.py`），默认不加载：未设置 `CAREEROS_ENABLE_LIEPIN=1` 时只返回 `EXTENSION_DISABLED` 与条款提示，不发起任何网络请求。它调用第三方平台接口，其使用范围由平台条款决定，启用即表示你自行确认授权范围；见 [猎聘接入](docs/LIEPIN_INTEGRATION.md)。

### 1.1 搜索到投递的统一记录

一个岗位的发布时间、JD、各平台招聘渠道、投递渠道、日程节点、状态和反馈，统一在一条记录里查看：

```powershell
python -m careeros jobs channels                          # 每个渠道能做什么、能否作为投递渠道
python -m careeros jobs route --provider official --query "产品经理" --location "上海"
python -m careeros jobs group                             # 同一岗位在多个平台的归并结果
python -m careeros jobs card --id 1                       # 单岗档案：JD + 渠道 + 投递 + 时间线 + 反馈
python -m careeros pipeline                               # 漏斗、重复投递提示、日程、数据缺口
python -m careeros application prepare --job-id 1 --resume-id 1 --channel boss --apply-url "https://..."
python -m careeros application event --id 1 --kind interview --label "一面" --scheduled-at "2026-10-22T14:00:00+08:00"
python -m careeros application agenda --days 30
```

同一公司同一岗位出现在多个平台时，`vacancy_groups` 会归并展示各平台渠道；`prepare` 返回 `already_applied_in_group` 提示，但**是否重复投递由你判断，系统不拦截也不自动去重**。详见 [统一记录](docs/APPLICATION_TRACKING.md)。

### 2. JD 分析

```powershell
python -m careeros analysis draft --job-id 1
python -m careeros analysis packet --job-id 1
python -m careeros analysis save --file data/private/analysis-1.json
```

`analysis draft` 只是逐行抽取的 `PRELIMINARY_UNKNOWN_MATCHES` 模板，所有匹配初始为 `unknown`。Codex 必须读取 packet，按原 JD 精确引文拆成 `hard_gate|core|preferred`，逐项映射经批准的经历 ID，并把公司资料保存为“事实 + 推断 + URL + 检索日期”。只有检查完整 JD 后才把 `coverage_confirmed` 设为 `true`。`analysis save` 校验这些映射并计算 `explore|apply|upskill|skip`，不替代语义判断。

### 3. 简历与七阶段红蓝评审

```powershell
python -m careeros resume build --job-id 1 --experience-ids 1,2 --headline "目标岗位"
python -m careeros review packet --resume-id 1
python -m careeros review save --file data/private/review-1.json
python -m careeros review list --resume-id 1
```

评审必须覆盖 `ats`、`hr`、`hiring_manager`、`technical`、`pressure`、`background`、`competition` 七阶段。红方只审 packet 中冻结的简历、JD、分析和来源；蓝方把每个 finding 转成 `wording|practice|evidence|retarget`。`pressure` 只做与岗位有关且尊重人的追问，不得基于受保护特征歧视；`competition` 是假设性市场基准，不得虚构其他申请者。

CLI 根据已审核的结构化输入计算结果：A 表示需求覆盖已确认、所有已知要求和七阶段均通过且来源仍新鲜；B 表示预计可过 ATS/HR 但仍有面试准备风险；C 表示筛选仍有可能但存在实质性短板；D 表示已知硬否决或无法靠改写解决的雇主/候选人不匹配。未知硬门槛通常返回 `NEEDS_EVIDENCE`，但已知 D 级否决优先；A 也绝不等于 offer 保证。

### 4. 反馈、改版、确认与复审

```powershell
python -m careeros feedback save --file data/private/feedback-1.json
python -m careeros feedback list --job-id 1
python -m careeros feedback plan --job-id 1
python -m careeros resume revise --file data/private/revision-1.json
python -m careeros resume confirm --id 2 --human-confirmed
python -m careeros resume history --id 2
python -m careeros review packet --resume-id 2
python -m careeros review save --file data/private/review-2.json
python -m careeros feedback resolve --id 1 --review-id 2 --note "已按反馈改版、确认并独立复审"
```

反馈必须标为 `actual|mock|hypothesis`。`actual` 必须绑定真实已提交的 application 和当时发送的精确 resume 版本；保存反馈不会自动修改申请状态，也不会自动提高等级。语义改写若产生原事实之外的新句子，必须由本人直接核实后才能执行 `resume confirm --human-confirmed`。改版后始终重新取 packet 独立复审；没有新证据时最多进行两轮红蓝循环，结构性缺口不能靠措辞修好。

### 5. 投递边界

```powershell
python -m careeros application prepare --job-id 1 --resume-id 2
# 用户自行在官方页面提交，并明确确认成功后：
python -m careeros application record --id 1 --status SUBMITTED --human-confirmed --note "User confirmed actual submission"
```

上述 record 只记账，不向网站发送任何内容。不得把个人经历、简历或反馈上传给第三方服务，除非用户针对该服务、用途和内容作出明确授权。

这也是"不会替你投简历"的具体含义：这里没有 submit API，没有浏览器自动化点击，没有批量投递队列。`--human-confirmed` 只用来记录你已经真实完成的一次投递，不是用来让系统替你投。海投在期望值上是负的——重复投递同一岗位、跨平台重复申请、投明显不匹配的岗位，都会降低而不是提高命中率；系统会把同一岗位的多平台来源归并并给出 `already_applied_in_group` 提示，但**最终判断仍然交给你**。

## 八个 Skills

| Skill | 负责内容 |
| --- | --- |
| `career-discovery` | 经历事实、证据与可迁移能力假设 |
| `career-mapping` | 相邻、跨行业与交叉职业方向 |
| `job-search` | 公开来源同步、授权导入、来源与快照 |
| `job-analysis` | 语义 JD 拆解、证据映射、未知硬门槛 |
| `resume-builder` | 证据锁定简历、红蓝评审与版本改写 |
| `application-assistant` | 本地申请包、人工投递和精确版本绑定 |
| `learning-planner` | 把实质性缺口转为可验收证据 |
| `interview-coach` | 公司资料、七阶段准备、模拟反馈 |

## 文档

- [ARCHITECTURE.md](docs/ARCHITECTURE.md)：Codex 与确定性 CLI 的责任边界
- [DATA_MODEL.md](docs/DATA_MODEL.md)：输入、版本、评审和反馈契约
- [WORKFLOWS.md](docs/WORKFLOWS.md)：端到端操作流程
- [SECURITY.md](docs/SECURITY.md)：隐私、外部来源和人工确认
- [EVALUATION.md](docs/EVALUATION.md)：自动化测试与人工验收
- [RESEARCH.md](docs/RESEARCH.md)：2026-10-18 有界现有方案调研
- [CHINA_JOB_SOURCES.md](docs/CHINA_JOB_SOURCES.md)：国内平台接入状态、聚合方案与实测
- [APPLICATION_TRACKING.md](docs/APPLICATION_TRACKING.md)：岗位/投递统一记录、多平台归并与重复投递判断
- [LOCAL_EXECUTION.md](docs/LOCAL_EXECUTION.md)：本地执行边界、缓存和 token 节省用法
- [ROADMAP.md](docs/ROADMAP.md)：已交付能力与后续边界

## 本地数据

- 数据库：`data/private/careeros.sqlite3`，可用 `CAREEROS_DB` 指定绝对路径。
- 私人导入和中间 JSON：`data/private/`。
- 简历草稿：`outputs/resumes/`。
- `data/private/` 和 `outputs/` 均被 Git 忽略，但 Git ignore 不是加密。

项目示例均为虚构记录。生产式使用前请用隔离数据库运行示例，且不要把示例 ID 当成真实个人资料。

## 参与贡献

- 开发约定与提交前检查见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题、隐私边界与漏洞上报见 [SECURITY.md](SECURITY.md)。
- 本项目不收集、不上传任何用户数据；请不要在 issue、PR 或讨论区粘贴真实简历、真实岗位库或招聘账号凭证。需要复现问题时，用 `data/examples/` 的虚构记录或自行脱敏后的最小样例。
- 改动后请跑 `python -m unittest discover -s tests -v`，并在 PR 描述里说明改了什么、为什么、验证方式。

## 许可证

[MIT](LICENSE) © 2026 CareerOS contributors。

第三方平台（Greenhouse、Lever、猎聘等）的接口、数据与商标归各自所有者，本许可证不授予任何平台接口的使用许可；相关合规责任见 [docs/SECURITY.md](docs/SECURITY.md) 与 [docs/LIEPIN_INTEGRATION.md](docs/LIEPIN_INTEGRATION.md)。
