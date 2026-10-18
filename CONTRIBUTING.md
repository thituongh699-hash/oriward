# 参与贡献

感谢你愿意改进 CareerOS。这个项目对"什么算合格改动"的要求比较具体，先花两分钟看完下面几条，能省掉一轮返工。

## 环境

```text
git clone <repo-url> careeros
cd careeros
python -m pip install -e .          # 可选；不装也能用 python -m careeros
python -m unittest discover -s tests -v
```

- Python 3.10+。核心 CLI 只用标准库，不引入第三方运行时依赖。`document-export` 的生成/校验库放在独立的 `documents` 可选依赖组中，只在导出时使用；不要在核心模块导入它们。
- 开发期可选装 ruff：`python -m pip install -e ".[dev]"`，配置在 `pyproject.toml`（当前只启用 `E9`/`F` 真实缺陷规则）。
- 命令中的 `python` 代表当前环境的 Python 3.10+ 解释器。主工作流不依赖特定 shell；CI 覆盖三个桌面系统，实际运行结果以对应的 Actions 记录为准。不要让默认工作流依赖 `.ps1` 或 `.sh` 辅助脚本。

## 提交前必做

1. `python -m unittest discover -s tests -v` 全绿；可选文档后端还需在提供 `documents` 依赖的环境运行导出测试。
2. 确认没有把本地状态带进提交：`git status` 中不应出现 `data/private/`、`outputs/`、`*.sqlite3`、`*.dpapi`。
3. 新增功能补测试；修 bug 优先补一个能复现该 bug 的测试。
4. 涉及外部网络、凭证、状态推进的改动，同步更新 `docs/SECURITY.md` 与对应契约文档。

## 代码约定

- **确定性优先**：`careeros/` 只做可复现计算与状态存储，不调用模型。语义判断交给上层 agent，不要把"智能"塞进 CLI。
- **一种事实一条写入路径**：事实、偏好、假设走 `belief propose`；修改用 `revise`，不做原地覆盖；只有用户本人指令才可 `confirm`。
- **推断保持推断**：`inferred` 状态的数据不得直接进入简历、候选名单或"我是谁"的陈述。
- **每个线程要有状态三元组**：`status`、`next_action`、`blocker`。缺 `suggestion_reason` 的 action 视为不完整记录。
- 边界情况明确失败优于静默降级：HTTP 200 不等于业务成功，未知硬门槛返回 `NEEDS_EVIDENCE` 而不是猜。
- 提交信息用 `feat|fix|docs|test|refactor|chore(scope): 说明` 的形式。

## 可选扩展规范（`careeros/extras/`）

新增第三方平台集成必须满足：

1. 放在 `careeros/extras/` 下，**不得**被 `careeros/` 在模块级导入；
2. 由独立环境变量开关控制，默认关闭；关闭时返回明确状态（参考 `EXTENSION_DISABLED`），且**零网络调用**；
3. 删除该文件不影响其余功能与测试；
4. 在 `docs/` 下补一份说明，写清：可用接口范围、凭证来源与存放、失败语义、平台条款由使用者自负；
5. 不在文档或 UI 中使用平台商标暗示官方合作。

## 隐私规则（硬性）

- 不要把真实简历、真实岗位库、招聘账号 Token、真实公司内部信息提交到仓库、issue、PR 或讨论区。
- 测试与示例只使用 `data/examples/` 的虚构记录，或明显虚构的占位值（如 `example.invalid` 域名）。
- 安全问题按 [SECURITY.md](SECURITY.md) 私下上报，不要开公开 issue。

## 当前不在范围内

以下方向**有意不做**，请勿为此提 PR（如确有需要，先开 issue 讨论，不要直接提交实现）：

- Docker 镜像与容器化部署
- Web UI / 图形界面 / 本地服务器
- PyPI 发布与自动发版流水线
- 多 LLM provider 适配层
- 任何形式的自动投递、批量投递、验证码绕过、登录态抓取

理由见 README 的"这个项目不会替你投简历，因为海投是负期望的"：投递量与命中率不是正相关，扩大自动化只会放大人力判断的缺失。
