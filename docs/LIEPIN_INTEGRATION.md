# 猎聘官方接入

核查时间：2026-10-18。官方授权入口：<https://www.liepin.com/mcp/auth>。
该页面目前链接官方 CLI 项目 <https://github.com/liepin-tech-2026/liepin-cil>，
没有展示可直接配置到 Agent 的标准 MCP server URL/transport。不能把授权页 URL 当作 MCP server。
核查源码提交：`858a62bd839d490e8745b7503961e4676a54b9d7`，CLI 版本 0.1.0。

## 可选扩展与条款（必读）

猎聘接入以**可选扩展**形式发布，位于 `careeros/extras/liepin.py`，默认**不加载、不导入、不发起请求**：

- 未设置 `CAREEROS_ENABLE_LIEPIN=1` 时，`jobs search --provider liepin` 返回 `EXTENSION_DISABLED`，附条款提示与启用方法，网络层零调用。
- 主包 `careeros/` 不在模块级引用该扩展，卸载或删除 `careeros/extras/` 不影响其余功能。
- 该扩展调用第三方平台接口。其开放范围、凭证使用条件与二次分发限制由平台条款决定；本仓库不对"第三方客户端可使用该接口"作任何承诺。
- 启用即表示使用者自行确认授权范围并承担相应责任。若你的使用场景无法确认合规，请改用 Greenhouse/Lever 公开 board、企业官网页面或手工导入。
- 不使用猎聘商标暗示官方合作或背书。

## 当前能力与验证边界

- 已实现标准库本地只读搜索适配器：`POST https://open-agent.liepin.com/mcp/search-job`，请求格式来自官方 CLI 的 `SearchJobInput`。
- 仅发送关键词、城市和首页页码。不读取账号简历，不改简历，不投递。
- 缺凭证明确返回 `AUTH_REQUIRED`；取得 HTTP JSON 也只返回 `RESPONSE_REQUIRES_VALIDATION`，不能视作成功职位搜索。
- 真实返回格式尚待用户授权验证；不猜测职位字段，不编造 ID/URL，不将业务错误导入职位库。
- 原始结果本地保存，返回文件路径；15 分钟账号隔离缓存保留原抓取时间。需要重新请求用 `-Refresh`。
- 只请求一页，30 秒超时、2 MiB 上限，禁止重定向转发凭证；没有批量轮询或自动重试。
- 未配置全局 MCP、Skill 或模型服务。安装的官方 CLI 仅作为核查参考，运行项目适配器不依赖它。

## 可选凭证辅助脚本

Python 搜索适配器从 `LIEPIN_USER_TOKEN` 环境变量读取凭证，不依赖 PowerShell。由宿主的安全凭证管理机制注入该变量，并在用户明确启用后设置 `CAREEROS_ENABLE_LIEPIN=1`，即可执行 `python -m careeros jobs search --provider liepin`。项目不提供通用的持久化密钥存储；不要把真实 Token 写进终端历史、聊天或仓库。

以下 `scripts/liepin.ps1` 只是 Windows DPAPI 凭证保存辅助脚本，不是主程序或该适配器的运行前提。

先由本人登录官方授权页并生成 Token。页面显示凭证有效期 90 天，重新生成会使旧凭证失效；
官方凭证也具备简历/投递能力，不能宣称凭证本身只有只读权限。本项目仅暴露搜索。

```powershell
pwsh -NoProfile -File ./scripts/liepin.ps1 -Setup
pwsh -NoProfile -File ./scripts/liepin.ps1 -Status
pwsh -NoProfile -File ./scripts/liepin.ps1 -Query '产品经理' -Location '苏州'
```

配置过程隐藏输入，用 Windows 当前用户 DPAPI 加密保存到忽略目录 `data/private/liepin-token.dpapi`。
不把 Token 放入聊天、命令行参数、源码、输出或普通配置文件。`-Status` 只说明本地是否有配置，不证明远程有效。
脚本默认使用 PATH 上的 `python`；换环境用 `-Python <绝对路径>` 指定解释器。
只在子进程执行期间通过 `LIEPIN_USER_TOKEN` 传递，并临时设置 `CAREEROS_ENABLE_LIEPIN=1`，随后恢复原环境变量，不改变 PATH。
官方 CLI 的 `setup` 会调用 `/mcp/get-resume` 验证凭证，所以本项目没有复用该流程。
原始响应与缓存位于 `data/private/liepin-search/`，供首次实测后确认业务状态、字段与入库契约。

## 与其他中国渠道的关系

BOSS 和智联仍通过连接的用户浏览器执行站内搜索，详见项目 job-search Skill 的 browser-search 引用。
猎聘是新增官方搜索入口，不替代这两个渠道。职页仍负责本地公开聚合搜索。
