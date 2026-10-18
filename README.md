# CareerOS · 面向在校生与应届生的 Agent 求职成长工作台（v0.2.0）

CareerOS 主要面向在校生与应届生：从“我还不知道自己能做什么”开始，让 Agent 随着一次次对话、课程项目、实习和求职反馈逐步了解你，把职业探索、学习提升、投递计划和面试准备接成一条可持续推进的路径。

求职推理交给你选择的大模型 Agent，可复现的校验、版本和状态交给本地 Python CLI + SQLite。取得仓库后，在 Claude Code（CC）、WorkBuddy、豆包等 Agent 工具中加载项目并开始对话；Agent 负责读取项目规则、检查运行环境和执行本地命令。实际执行需要宿主开放文件和终端权限，各工具尚未逐一完成原生适配验证。

你不需要先有一份漂亮简历或明确的职业答案。先从一段真实经历和一个能完成的小行动开始，逐步积累可核查的能力证据；Agent 的判断可以讨论、修订，不替你定义个人价值。项目内 8 个工作流 Skills 约束从经历发现、岗位采集、JD 分析、红蓝评审、简历改版到真实反馈复盘的过程。

第一次使用请看独立的 [用户入门手册](docs/USER_GUIDE.md)，其中包含环境准备、首次对话、学期与求职计划，以及换工具后如何继续。

v0.2 的产品核心是 **Career Twin Core**：一个带来源、置信度和版本链的用户状态中枢，向 8 个工作流 Skills 提供统一的读写接口与上下文摘要。它持续回答五个问题——我是谁、我可能成为谁、我现在在哪、下一步做什么、你凭什么这么认为。设计见 [docs/CAREER_TWIN_CORE_ARCHITECTURE.md](docs/CAREER_TWIN_CORE_ARCHITECTURE.md)。

当前版本可以读取公开的 Greenhouse/Lever job board、只读解析企业官网单岗页面（JSON-LD JobPosting 优先）、导入 JSON/CSV、保存不可变岗位快照、把同一岗位在多个平台的来源归并分组、记录发布时间/投递渠道/日程节点与反馈，生成证据约束的 Markdown 简历、冻结具体简历与 JD 版本进行七阶段模拟招聘评审，并追踪改版与反馈。它不会自主调用外部模型、登录招聘账号、代投、联系招聘方或绕过验证码。所谓 A–D 是本地模拟审查结果，不是雇主决定或 offer 概率。

> **这个项目不会替你投简历，因为海投是负期望的。**
>
> 从认识自己到积累证据，从安排学习到准备投递，把每一步做得更清楚。还在探索时，先找到可以验证的方向；临近求职时，再结合真实岗位安排准备与投递。最后的提交动作由你本人在官方页面完成并确认。
>
> 相应地，系统不保存招聘账号密码、不模拟点击、不绕过验证码、不代发消息，也不提供"一键海投"。这类功能不是没做，是刻意不做。

## 目录

- [快速开始](#快速开始)
- [当前招聘闭环](#当前招聘闭环)
- [Skills](#skills)
- [文档](#文档)
- [本地数据](#本地数据)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

## 快速开始

1. 下载或克隆本仓库，把项目文件夹加载到你使用的 Agent 工具中。
2. 允许 Agent 在该项目范围内读取文件和执行命令，然后发送下面这段话。
3. 从一段真实经历开始；后续的资料保存、学习安排和投递跟进都由 Agent 按项目规则协助完成。

```text
请读取这个项目的 AGENTS.md，按首次使用流程检查环境并初始化 CareerOS。
我目前是[年级/毕业年份]，正在[探索方向/找实习/准备校招]。
先按 career-discovery 从一段真实经历开始，一次问我两三个问题。
请把事实、推断和未知分开，最后留下已保存的记录和一个我愿意完成的小行动。
```

主程序只使用 Python 3.10+ 标准库，不要求先安装项目或额外服务。Agent 会选择宿主可用的解释器，按需创建本地数据库；如果确实缺少运行时或执行权限，会报告具体缺项。完整流程见 [用户入门手册](docs/USER_GUIDE.md)。

## 当前招聘闭环

```text
公开来源/API 或授权导出 -> 岗位快照 -> Agent 语义分析 -> 证据约束简历
-> 红方七阶段审查 -> 蓝方 finding-to-action -> 改版与真人事实确认
-> 独立复审 -> 人工投递 -> 真实/模拟/假设反馈分流 -> 下一轮行动
```

命令与状态推进的完整序列见 [WORKFLOWS.md](docs/WORKFLOWS.md)。最小示例（由 Agent 执行，路径按实际替换）：

```text
python -m careeros jobs import --json data/private/jobs.json
python -m careeros analysis packet --job-id 1 --compact
python -m careeros resume build --job-id 1 --experience-ids 1,2 --headline "目标岗位"
python -m careeros application prepare --job-id 1 --resume-id 1
```

三条边界贯穿全流程：

- **来源**：`jobs show` 同时给出 freshness；fresh 只说明来源检索时间较近，不保证岗位仍开放。手工导入缺少 `retrieved_at` 时保持 unknown，较旧记录不能覆盖较新观察。
- **分析**：`analysis draft` 只是全 `unknown` 的行模板；Agent 必须读取 packet，按原 JD 精确引文拆成 `hard_gate|core|preferred`，只有检查完整 JD 后才把 `coverage_confirmed` 设为 `true`。
- **投递**：`application prepare` 只生成 `READY_FOR_USER`。用户本人在官方页面提交并明确确认后，才可 `application record --status SUBMITTED --human-confirmed`；它只记账，不向网站发送任何内容。

国内渠道、归并规则、缓存与可选扩展分别见 [中国渠道](docs/CHINA_JOB_SOURCES.md)、[统一记录](docs/APPLICATION_TRACKING.md)、[本地执行](docs/LOCAL_EXECUTION.md)、[猎聘接入](docs/LIEPIN_INTEGRATION.md)。猎聘默认关闭，未设置 `CAREEROS_ENABLE_LIEPIN=1` 时只返回 `EXTENSION_DISABLED`，不发起网络请求。

## Skills

八个职业工作流，加一个按需使用的文档交付技能。PDF/DOCX 生成使用宿主已有运行时或 `documents` 可选依赖，不影响核心 CLI 的轻量启动。

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
| `document-export` | 把已生成的简历或审核后的职业文档转成 DOCX/PDF，只做格式转换，并检查渲染后的页面 |

## 文档

- [ARCHITECTURE.md](docs/ARCHITECTURE.md)：Agent 与确定性 CLI 的责任边界
- [USER_GUIDE.md](docs/USER_GUIDE.md)：面向在校生与应届生的完整入门路径和不同 Agent 工具的接入方式
- [DATA_MODEL.md](docs/DATA_MODEL.md)：输入、版本、评审和反馈契约
- [WORKFLOWS.md](docs/WORKFLOWS.md)：端到端操作流程（命令与状态的唯一完整序列）
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
- 本地 CLI 不调用模型服务；你选择的 Agent 在分析材料时可能将读取的内容交给其模型服务，具体以该工具的数据处理方式和你的授权为准。请不要在 issue、PR 或讨论区粘贴真实简历、真实岗位库或招聘账号凭证。需要复现问题时，用虚构或脱敏的最小样例。
- 改动后请跑 `python -m unittest discover -s tests -v`，并在 PR 描述里说明改了什么、为什么、验证方式。

## 许可证

[MIT](LICENSE) © 2026 CareerOS contributors。

第三方平台（Greenhouse、Lever、猎聘等）的接口、数据与商标归各自所有者，本许可证不授予任何平台接口的使用许可；相关合规责任见 [docs/SECURITY.md](docs/SECURITY.md) 与 [docs/LIEPIN_INTEGRATION.md](docs/LIEPIN_INTEGRATION.md)。
