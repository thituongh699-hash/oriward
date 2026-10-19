# CareerOS

面向在校生与应届生的本地求职成长工作台。你选择的 Agent 负责理解与判断，项目内 8 个职业技能负责探索、搜岗、简历、学习和面试流程，Python CLI + SQLite 保存来源、版本、决定与进展；另有一个纯格式转换的 DOCX/PDF 导出技能。

## 开始使用

将项目文件夹加载到能读取文件和执行终端命令的 Agent，发送：

> 请读取 AGENTS.md，按首次使用流程检查环境并启动 CareerOS。我目前在探索方向/准备求职，每周约有……小时。先从我现在最需要解决的一件事开始。

主程序需要 Python 3.10+，只用标准库，无需先安装项目。各宿主的文件权限、终端和技能发现能力以实际可用情况为准；仅聊天模式不会自动保存资料或取得实时岗位。

## 按需读取

| 需要什么 | 入口 |
| --- | --- |
| Agent 共享规则和技能路由 | [AGENTS.md](AGENTS.md) |
| 首用、探索、招聘闭环与跨会话接续 | [WORKFLOWS.md](docs/WORKFLOWS.md) |
| 输入结构、版本和状态约束 | [DATA_MODEL.md](docs/DATA_MODEL.md) |
| 推荐依据、约束核实、用户选择与后续结果 | [DECISIONS.md](docs/DECISIONS.md) |
| 职位来源和渠道限制 | [CHINA_JOB_SOURCES.md](docs/CHINA_JOB_SOURCES.md) |
| 猎聘可选扩展配置 | [LIEPIN_INTEGRATION.md](docs/LIEPIN_INTEGRATION.md) |
| 变更与历史验收边界 | [CHANGELOG.md](CHANGELOG.md) |

普通任务只需读取 AGENTS 和相关技能；详细契约在需要执行对应操作时再读。

## 数据与操作边界

默认数据库为 `data/private/careeros.sqlite3`，简历和导出文件在 `outputs/`；Git 忽略不等于加密。本地 CLI 不调用模型服务，但宿主 Agent 读取的材料可能由其模型服务处理。迁移备份不包含全部附件，换机器还需备份文件并核对登记路径。

项目不代投、不登录账号、不联系招聘方、不绕过验证码。用户亲自提交后才记录投递事实。来源时间不代表岗位仍开放；A–D 是本地模拟审查结果，不是录用概率。DOCX/PDF 导出只转换已有内容，不确认事实或推进求职状态。

安全问题请优先通过仓库的私有漏洞上报入口联系维护者；若未启用，先只请求私下沟通渠道。不要在公开 issue、PR 或聊天中暴露凭证、真实简历或他人资料。

## 开发与许可

维护规则见 AGENTS。运行 `python -m unittest discover -s tests -v`；需要验证导出时安装可选 `.[documents]` 依赖。CLI 演示使用新建隔离目录和虚构数据，入口见 WORKFLOWS。

采用 [MIT 许可证](LICENSE)。第三方接口、数据与商标归原所有者；项目许可证不授予平台访问许可。
