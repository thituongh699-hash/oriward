# CareerOS 用户入门手册：从在校探索到毕业求职

CareerOS 是一个本地求职准备工具。它帮助你把零散的经历整理为可核查的材料，逐步探索方向，记录岗位、学习计划、简历版本和真实反馈。它适合还在读书、刚毕业、方向尚未确定，但愿意留出一点时间慢慢了解自己、做计划、学习并认真申请的人。

它不替你决定人生，也不承诺 offer。职业方向、匹配程度和招聘结果都要随着证据、岗位和你的选择更新。你可以先从一段课程项目、社团工作、照顾家人、一次失败、兼职或兴趣投入开始；暂时说不清也没有关系。

> **海投是负期望的。**
>
> 这个工具用于提高每一次认真申请的准备质量，不提供批量投递、自动登录、绕过验证码或替你点击提交。最终提交由你本人在招聘方页面完成。

## 你会得到什么

完成一轮基础使用后，你应当有：

- 一份区分了本人确认事实、推断和未知项的经历库；
- 两三个待验证的方向假设，以及它们的支持证据、短板和下一步；
- 一份有时间预算和验收结果的学习或准备计划；
- 已保存来源和日期的岗位记录，而不是聊天里的一串链接；
- 针对一个具体岗位的 Markdown 简历草稿、版本记录和待确认事项；
- 由你自行完成提交后留下的投递、面试和反馈记录。

没有任何一步要求你一次讲完自己的故事。每次补充一件真实的小事，下一次继续即可。

## 开始前

### 把仓库加载到你的 Agent

从项目的实际 GitHub 仓库页面克隆或下载并解压，将整个项目文件夹加载到你的 Agent 工具中。根目录应当能看到 `AGENTS.md`、`pyproject.toml`、`careeros/` 和 `docs/`。允许 Agent 在项目范围内读取文件和执行命令，然后让它读取 `AGENTS.md`，按首次使用流程启动。

运行环境检查、选择 Python 解释器、初始化本地数据库和读取当前进度由 Agent 完成；你不需要先逐条运行安装命令。主程序只使用 Python 3.10+ 标准库。如果宿主缺少运行时或没有执行权限，Agent 应明确指出缺项，不能把“加载了文件”说成“已经运行成功”。

本手册中的命令块是给 Agent 执行或供你核查的参考，不是入门前必须完成的清单。命令以 `python` 示意，Agent 应使用检查到的实际解释器；`<ID>` 等占位符要换成实际命令返回值，JSON 输入由 Agent 按对应 Skill 契约生成。默认数据库在 `data/private/careeros.sqlite3`，简历草稿在 `outputs/resumes/`；Git 忽略不等于加密。

### 先跑一遍虚构演示

想先看看完整流程，可以对 Agent 说：“先用虚构数据演示一遍，不导入我的真实资料。”由它选择一个不存在的输出目录并运行：

```text
python scripts/demo_hiring_loop.py --output outputs/hiring-loop-demo-local
```

演示会在该输出目录创建独立 SQLite、虚构候选人、虚构岗位、两版简历和 `REPORT.md`。它不会读取或污染你的真实数据库，也不会联网或投递。它只证明这条工作流能够走通，不能证明你会获得面试或录用。

`data/examples/` 中也都是虚构材料。尤其不要把 `data/examples/analysis.json` 当作自己的有效分析导入：真实岗位分析应从当前岗位的 `analysis draft` 和 `analysis packet` 开始，再由你确认其中的事实与判断。

## 两种使用方式

### 方式一：有文件和终端的 LLM Agent

这是完整工作流。Agent 读取项目说明和当前需要的 Skill 文件；你与它对话、确认事实；它把审核过的 JSON 保存到 `data/private/`，再运行 CLI 写入本地数据库。这样后续换聊天、换工具或隔几天再回来，仍可由数据库和文件接续。

每次新的实质会话，先运行：

```text
python -m careeros context brief
```

它会返回一个有长度上限的摘要和记录 ID。需要细节时再查，而不是把整个数据库塞进对话：

```text
python -m careeros context why --assertion-id <ID>
python -m careeros experience list
python -m careeros action list
```

如果你的工具不能自动发现项目 Skill，请把下面这段作为首次提示词复制给 Agent。它不依赖某种专有的 Skill 调用语法。

```text
我在使用 CareerOS。请先阅读项目根目录的 AGENTS.md。
若是首次使用，请替我检查运行环境、选择解释器并初始化本地数据库。
本轮先运行 `python -m careeros context brief`，只读取解决本轮问题所需的记录。
再按我的目标阅读相关的 `.agents/skills/<skill 名称>/SKILL.md`：
经历探索用 career-discovery；方向探索用 career-mapping；岗位用 job-search 或 job-analysis；
简历用 resume-builder；学习用 learning-planner；面试用 interview-coach；投递跟进用 application-assistant。
请把“我确认的事实”“你的推断”“未知/待验证项”分开。不要编造经历、指标、职位或招聘结果。
草稿和推断可以按本轮授权保存；事实进入简历或标为“用户已确认”前，先让我核实具体表述。
保存到 data/private/ 并运行相应的 CLI 命令后，报告实际生成的 ID 与路径。
不要登录招聘网站、上传文件、发送消息或替我提交申请。
```

这套文件加终端流程可用于 Claude Code（CC）、WorkBuddy、豆包或任何能读取项目文件并执行本地命令的 LLM Agent。不同工具是否能读取文件、运行 shell、保留工作目录，由该工具和你的权限决定；仅有一个聊天窗口并不会自动获得 CLI 访问权限。

还不知道怎么开始时，可以接着说：

```text
我目前是[年级/毕业年份]，正在[探索方向/找实习/准备校招]，每周大约能留出[小时]。
我现在最困扰的是[你自己的描述]。先别要求我一次规划完整个职业生涯。
请按 career-discovery 从一段课程、项目或生活经历开始，一次问我两三个问题。
今天结束时，帮我留下已确认的事实、待验证的方向和一个我愿意完成的小行动。
```

第一轮的完成标准很小：一段已核实的经历、尚未定论的问题，以及一个下次可接着做的行动。你可以拒绝建议或调整节奏。

### 方式二：只有聊天窗口

只有聊天的 LLM 仍可帮你梳理经历、比较方向、改写草稿和准备问答，但它看不到本地数据库，也不会自动保存对话。你可以在自己的终端运行它给出的命令，再只分享必要的脱敏输出；如果暂时也没有终端，先手动保留已确认内容，例如自己的 Markdown 笔记，以后再按项目的 Skill 契约整理成 JSON 导入。

聊天工具没有已验证的专用平台适配器。不要因为 Agent 能讨论岗位，就认为它已经读取到实时职位、登录了平台、创建了数据库，或会在后台持续提醒你。职位链接、岗位全文、来源日期和你确认过的事实，需要由你手动粘贴、上传或在有文件与终端的环境中保存。

## 从认识自己开始

对还在读书或刚毕业的人，最有价值的不是立刻选一个“唯一正确”的岗位，而是先积累真实证据。一次会话只选两三类问题即可：

- 课程、作业、竞赛、实验、毕业设计：你具体负责什么，解决了什么问题？
- 社团、志愿、组织和兼职：你如何协调人、信息、时间或现场？
- 个人项目、创作和长期兴趣：你做过哪些可展示的版本、作品或复盘？
- 家庭照护、迁移、空档期和挫折：它带来了哪些约束、责任或学习，而不是强迫你把它包装成成就？
- 失败、放弃和不喜欢的事：它说明了什么工作条件、节奏或任务不适合你？

先查看已有资料：

```text
python -m careeros profile show
python -m careeros experience list
```

与 Agent 讨论后，由 Agent 依据 `career-discovery` 的合同草拟文件；你逐句确认事实后才保存：

```text
python -m careeros profile save --file data/private/profile.json
python -m careeros experience add --file data/private/experience-course-project.json
python -m careeros experience list
```

进入简历的经历必须是你确认过的，而且 `approved_for_resume=true`。Agent 认为你“可能擅长”的东西只能是推断，不能因为说得顺就变成个人履历。

如果要保存一条长期判断或偏好，让 Agent 先提出带来源的断言，再由你决定是否确认：

```text
python -m careeros belief propose --file data/private/belief-direction.json
python -m careeros belief list --limit 20
python -m careeros belief confirm --id <ID> --note "我确认这个表述准确"
```

确认不是形式动作。你不同意、证据变了或只是暂时猜测，都应保留为不同状态，而不是硬改成事实。

## 把方向当作可验证的假设

有了两三段经历后，请让 Agent 用 `career-mapping` 提出少量相邻、跨行业或混合方向。每个方向至少应说明：

- 支持它的具体经历 ID；
- 仍然缺少或反驳它的证据；
- 已知硬门槛，例如专业、作品、资格或工作地点；
- 能用小成本验证的下一步，例如看五个真实 JD、完成一个小作品或找一位从业者了解工作；
- 是“已验证事实”还是“方向假设”。

保存经过你审核的方向，并记录真正想推进的目标：

```text
python -m careeros career add --file data/private/career-direction.json
python -m careeros career list
python -m careeros goal add --file data/private/goal-product-role.json
python -m careeros goal list
```

方向不需要现在定终身。它的完成标准可以是“读完十个岗位要求并完成一页对比”，而不是“必须找到工作”。

## 规划学习时间和截止日期

把短板分成三类：需要练习回答、需要可展示的证据、或需要换目标层级/方向。学习计划应写清每项的产出、验收标准、预计投入和日期；上完课程本身不等于已经具备岗位能力。

先告诉 Agent 毕业时间、考试周、可实习时间、地域或经济约束，以及每周能投入多少小时。让它拟定少量目标，由你决定先推进哪一个。以下是可调整的阶段安排，不是每个人必须完成的时间表：

| 当前阶段 | 本轮重点 | 可检查的结果 |
| --- | --- | --- |
| 方向还不清楚 | 整理两段经历，比较两三个方向 | 有支持与反驳证据的方向假设 |
| 距离投递还有时间 | 看少量真实 JD，选一个差距做作品 | 一个有验收标准、适合课余完成的产出 |
| 实习或校招窗口临近 | 核对资格、截止日期和准备成本 | 按优先级与日期排列的小批量投递计划 |
| 已有投递或面试 | 记录结果，区分能力缺口与未知原因 | 下一轮练习、补证据或调整目标的行动 |

投递计划应逐项写出岗位 ID、资格/截止日期来源、拟用简历版本、准备任务、预计投递日期和阻塞点。Agent 将这些落到目标、行动和岗位记录里；没有查到的截止日期保持未知。每周回来看实际完成了什么，再决定是否缩减或调整计划。

```text
python -m careeros learning save --file data/private/learning-plan.json
python -m careeros learning list
python -m careeros action propose --file data/private/action-portfolio.json
python -m careeros action list --sort due
```

日期会保存在本地记录并用于排序，但项目不会在后台主动推送提醒，也不承诺电脑关闭后仍会通知你。请把关键日期同步到你实际使用的日历或待办工具，并定期自己运行 `action list`。完成时保留可核查的作品、代码、报告或复盘，再把它作为新经历进行确认。

```text
python -m careeros action complete --id <ID> --human-confirmed --evidence "作品或复盘的位置"
```

## 找到真实岗位并保存来源

岗位库的意义是保存“看到了什么、从哪里来的、何时取得”，不把搜索计划当成搜索结果。

先查看当前渠道能力：

```text
python -m careeros jobs channels
```

当前可实际同步的是公开 Greenhouse 和 Lever job board（`BOARD_SLUG` 是招聘方公开标识，不是公司中文名）；企业官网单岗页用 `official plan/fetch`；国内平台使用你有权导出的 JSON/CSV；本地公开线索用 `jobs search`。

```text
python -m careeros jobs sync --provider greenhouse --board <BOARD_SLUG> --company "<公司>" --limit 20
python -m careeros official fetch --url "https://<企业职位页>" --company "<公司>"
python -m careeros jobs import --json data/private/jobs.json
python -m careeros jobs search --provider zhiye --query "数据分析实习" --location "<目标城市>" --limit 5
```

完整渠道与参数见 [WORKFLOWS 第 2 节](WORKFLOWS.md#2-建立方向并取得真实岗位样本) 与 [中国渠道](CHINA_JOB_SOURCES.md)。`search` 的线索不等于完整 JD 或仍在招聘；项目不提供登录态抓取、验证码绕过或已验证的 BOSS 直聘专用接入。导入或同步后，检查单岗完整内容、来源时间和状态：

```text
python -m careeros jobs show --id <岗位ID>
python -m careeros jobs card --id <岗位ID>
python -m careeros pipeline ensure --job-id <岗位ID>
```

对每个准备跟进的岗位执行一次 `pipeline ensure`，才能进入核心机会视图。由 Agent 在分析后用 `pipeline update` 记录评估、候选、暂缓或放弃及其理由。`fresh` 只表示已知读取时间较近，`listed` 也不是雇主仍接受申请的保证。没有来源日期的手工导入会保持 unknown，不应由 Agent 补写成“最新”。

## 分析一个岗位，再写一份 Markdown 简历

确定一个具体岗位后，先生成本地模板和完整分析包：

```text
python -m careeros analysis draft --job-id <岗位ID>
python -m careeros analysis packet --job-id <岗位ID> --compact
```

让 Agent 根据 `job-analysis` 逐条检查完整 JD。每项要求应保留 JD 原文，标为硬门槛、核心或加分项，并且把“已满足”“缺口”“未知”分开。没有证据时保持 unknown；不要让模型为了给出高分而猜测。

审核完成后保存分析：

```text
python -m careeros analysis save --file data/private/analysis-<岗位ID>.json
```

只选你确认且允许用于简历的经历，生成岗位定制的 Markdown 草稿：

```text
python -m careeros resume build --job-id <岗位ID> --experience-ids <ID1,ID2> --headline "<目标岗位>"
python -m careeros resume list
python -m careeros review packet --resume-id <简历ID> --compact
```

Agent 按 `resume-builder` 审查七个角度：可解析性、招聘初筛、用人负责人、专业能力、岗位相关追问、材料一致性和公开要求下的竞争风险。它会指出风险和行动，不能替雇主作决定；即使得分高，也不代表 offer。

保存审核后的评审文件：

```text
python -m careeros review save --file data/private/review-<简历ID>.json
python -m careeros review list --resume-id <简历ID>
```

如果修改措辞，先保存改版，再由你阅读完整新句子并确认真实性：

```text
python -m careeros resume revise --file data/private/revision-<简历ID>.json
python -m careeros resume confirm --id <新简历ID> --human-confirmed
python -m careeros resume history --id <新简历ID>
```

每次实质改版都要重新取得 `review packet` 并独立评审。没有新证据时，两轮红蓝改写后就应停止润色循环：把真正的短板转成练习、作品证据或调整目标。

## 由你本人提交，并记录真实反馈

确认岗位 URL、投递渠道、所用简历版本和回答内容后，先准备本地申请记录：

```text
python -m careeros application prepare --job-id <岗位ID> --resume-id <简历ID> --channel <渠道> --apply-url "https://<实际提交页面>"
```

这一步只产生 `READY_FOR_USER`，不会上传或提交。请在招聘方网站自行完成申请。只有你已经真实提交并明确确认后，才记录提交：

```text
python -m careeros application record --id <申请ID> --status SUBMITTED --human-confirmed --note "本人已在官方页面提交"
```

记录面试、笔试或提醒自己查看进度的日期：

```text
python -m careeros application event --id <申请ID> --kind interview --label "一面" --scheduled-at "2026-10-22T14:00:00+08:00"
python -m careeros application agenda --days 30
python -m careeros application timeline --id <申请ID>
```

收到结果后，把它区分为真实反馈、模拟反馈或尚未验证的解释。一次拒绝只是一次观察，不自动证明你“不适合”某个方向：

```text
python -m careeros feedback save --file data/private/feedback-<申请ID>.json
python -m careeros feedback list --job-id <岗位ID>
python -m careeros feedback plan --job-id <岗位ID>
```

## 换工具、换聊天和隐私

可以在不同 LLM Agent 间切换。每次切换后，先让新 Agent 读取 `AGENTS.md`、本轮相关 Skill 文件，并运行 `context brief`；只针对需要的 ID 展开内容。这样既减少不必要的个人信息暴露，也避免把完整简历、所有聊天和全部岗位一次塞进上下文。

对话本身不是项目的持久记忆。通过 CLI 写入 SQLite 的结构化记录才会进入后续查询和摘要；把 JSON、笔记或附件放进 `data/private/` 并不会自动导入，还需显式读取或用对应命令保存。`outputs/` 中的已登记简历要与数据库中的版本和文件路径配套。换工具时先读取摘要，再按 ID 或明确路径查资料，不要声称“上次聊天已经保存”，除非命令输出或文件能够证明对应操作成功。

本地 CLI 不会自行把数据库上传给模型服务；但你粘贴到聊天、上传给 Agent，或授权某个工具读取的内容，可能会由该服务处理。使用前查看该服务自己的隐私设置；不要在聊天中提供账号密码、身份证件、银行卡信息或不必要的他人隐私。

有资料的数据库升级时会生成本地迁移备份，但它不包含所有简历与附件，也没有一键恢复全部资料的命令。请另外备份数据库、`data/private/` 中需要的输入文件，以及 `outputs/` 中的简历版本。切换工具时指向同一个项目和数据库；迁移到另一台电脑还需保留文件路径或核对登记路径，单独复制聊天记录或数据库并不保证简历文件可用。不要把这些私人材料提交到公开仓库。

## 常见问题

### 我没有实习经历，能开始吗？

能。课程、社团、个人项目、兼职、志愿活动、照护责任、失败后的复盘都可能是线索。它们是否能用于某份简历，取决于你能否说清本人行动、证据和岗位相关性，而不是经历名称是否“漂亮”。

### Agent 说我适合某个岗位，这是真的吗？

这是待验证的方向假设，除非它有你确认的经历证据和已核查的岗位要求。请保留支持与反驳证据，先用小任务、真实 JD 或作品验证，再决定投入多少时间。

### 为什么不会自动搜索所有平台或自动投递？

公开 Greenhouse/Lever 有明确的只读同步入口；其他平台受登录、授权和条款限制。项目也刻意不做代投。它可保存你确认的来源、申请版本、渠道和反馈，让你自己决定每次认真申请。

### A、B、C、D 是录用概率吗？

不是。它们是基于当前资料的本地模拟评审标签。未知硬门槛会要求补证据；高等级不保证录用，低等级也不评价你的价值。

### 我能用它做简历吗？

能。`resume build` 生成 Markdown 简历草稿，后续通过版本、事实确认和独立评审管理。想要可编辑 Word 和 PDF 时，对 Agent 说“把简历版本 ID 导出成 DOCX 和 PDF”，它会使用 `document-export` 做格式转换并检查字体和页面；转换不改变任何记录，也不代表已经投递。学习计划、投递计划与面试准备笔记也可生成这两个格式。

### 如何知道下一步？

先运行：

```text
python -m careeros context brief
python -m careeros action list --sort due
python -m careeros pipeline
```

从一个最小动作开始：补一段经历、验证一个方向、读取一个完整 JD、完成一个作品，或为一场面试准备一个案例。完成后记录证据，再继续下一步。
