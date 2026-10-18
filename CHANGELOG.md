# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
