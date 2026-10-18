# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 文档交付

- 新增项目内 `document-export` 技能及本地导出脚本，把已生成的简历或审核后的结构化内容转成 DOCX/PDF。
- 转换只改变格式：不写数据库、不确认事实、不改变评审等级或投递状态；待事实确认的简历改版会被拒绝导出。
- 简历必须用 `--resume-id` 转换已登记版本，结构化输入只用于学习/投递计划、面试笔记和报告；形似简历的结构化输入会被拒绝。
- 生成依赖只放在可选组中；默认启动仍使用标准库。

### Career Twin Core 修正

- 已废弃的断言版本不能再被确认、存疑或撤回，避免同一单值属性出现两条“当前有效”记录。
- 低置信的模糊自述先进入 `uncertainties`，确认后才进入“我是谁”，不再直接固化为价值观或能力标签。
- `job_pipeline` 增加 `goal_id`、`next_actions` 增加 `effort_hours`（schema v3），排序可以解释“服务哪个目标、预计投入多少”。
- 排序权重与架构文档对齐；已取消的前置行动不再静默放行后续行动，阻塞中的行动必须先解除阻塞才能完成。
- `signal add` 校验目标对象存在；`signal promote` 必须带 `--human-confirmed`，一次反馈不会由 Agent 自行升级为长期约束。
- `reflection decide --accept` 记录用户实际批准了哪几条提案，而不是只留一句备注。
- 单岗视图的阶段取最靠后的申请状态，并标出“最近事件是否经用户确认”。

### 启动入口与可移植性

- 首次使用统一为“取得仓库、加载到 Agent、开始对话”；由 Agent 检查 Python/SQLite、初始化本地记录并读取进度，不要求用户先照着分平台命令安装。
- 通用命令块取消 PowerShell 标记，移除浏览器辅助示例中固定的可执行文件名；保留真实依赖 Windows DPAPI 的可选凭证脚本及其边界。
- 缺少猎聘凭证时返回通用配置文档与环境变量名；不再把 Windows 辅助脚本当作通用必需步骤。
- CI 增加 Windows 和 macOS 作业，保留 Linux 的 Python 版本覆盖，禁用扩展检查改用可移植 Python 步骤，并增加隔离端到端演示。

### 用户指引与定位

- 新增独立的 `docs/USER_GUIDE.md`，覆盖环境准备、首次对话、学生经历梳理、学习与投递计划、复盘及更换 Agent 工具后的续接。
- 主要用户定位为在校生与应届生；让理解、能力证据和求职安排随多次会话逐步积累，尊重学业负担与用户节奏。
- 项目指引、架构文档和环境检查改为工具无关的 Agent 表述，说明自动执行与用户手动配合的能力条件，不把未实测的厂商集成标为已验证。
- 保留“海投是负期望的”作为项目标语。

### 变更

- 猎聘渠道从主包迁至 `careeros/extras/liepin.py`，改为默认关闭的可选扩展：未设置 `CAREEROS_ENABLE_LIEPIN=1` 时返回 `EXTENSION_DISABLED` 且不发起网络请求；主包不再在模块级引用该模块。
- `scripts/liepin.ps1` 的 Python 解释器参数默认值改为 PATH 上的 `python`，可用 `-Python` 覆盖；运行期间临时设置 `CAREEROS_ENABLE_LIEPIN=1`，结束后恢复。
- `scripts/smoke_twin_core.sh` 的解释器改为 `PYTHON` 环境变量可覆盖；示例夹具改为中性的虚构值。
- 仓库文档中的本机绝对路径改为占位符或可配置参数。

### 新增

- `LICENSE`（MIT）。
- `README.en.md`：英文精简版，含"不会替你投简历"的边界说明。
- 根目录 `SECURITY.md`、`CONTRIBUTING.md`、`CHANGELOG.md`。
- `.github/workflows/tests.yml`：Python 3.10 / 3.12 / 3.13 矩阵，编译检查与全量单元测试。
- `pyproject.toml` 补齐 license、readme、authors、classifiers、可选 dev 依赖；包发现改为 `include = ["careeros*"]`。
- README 增加目录、示例数据导入、参与贡献与许可证段。

### 测试

- 新增 1 个用例：可选扩展默认关闭时返回 `EXTENSION_DISABLED` 且不触发网络调用（合计 132 个）。

## [0.2.0] - 2026-10-18

### 新增

- Career Twin Core：带来源、置信度与版本链的用户状态中枢（断言、目标、流水线、行动、信号、上下文预算、反思提案）。
- `context brief` 有界五问摘要与 `context why` 钻取。
- 岗位来源：Greenhouse/Lever 公开 board 同步、企业官网单页 JSON-LD 解析、JSON/CSV 导入、不可变快照。
- 多平台同岗位归并分组、投递渠道与日程节点、`already_applied_in_group` 重复投递提示。
- 证据约束简历生成、冻结 JD/简历版本的七阶段红蓝评审、`actual|mock|hypothesis` 反馈分流与改版复审。
- 八个 `.agents/skills/` 编排技能。

### 说明

- 不提供自动投递、账号登录、验证码绕过或外部消息发送；`application record` 只记录用户已确认的真实投递。
- A–D 评级为本地模拟审查结果，恒带 `SIMULATED_HIRING_REVIEW_NOT_EMPLOYER_VERDICT`。
