# 猎聘搜索扩展

`careeros/extras/liepin.py` 是默认关闭的可选扩展，仅暴露关键词/城市搜索；不读取或改写简历，不投递。接口使用范围由平台条款与用户授权决定，项目不承诺第三方客户端许可，也不暗示官方合作。代码具备接口不等于当前账号或远端已验证可用；历史核查见 [CHANGELOG](../CHANGELOG.md)。

## 启用与返回状态

没有用户明确指令不得启用。宿主安全注入 `LIEPIN_USER_TOKEN` 并设置 `CAREEROS_ENABLE_LIEPIN=1` 后执行：

```text
python -m careeros jobs search --provider liepin --query "产品经理" --location "苏州" --limit 10
```

| 返回 | 含义与下一步 |
| --- | --- |
| `EXTENSION_DISABLED` | 未启用，扩展不加载、网络零调用；不等于无结果 |
| `AUTH_REQUIRED` | 缺凭证或 HTTP 401/403；需用户处理授权，不算搜索成功 |
| `REQUEST_FAILED` 或校验异常 | 请求/内容失败，未导入岗位；不打印可能回显凭证的远端错误正文 |
| `RESPONSE_REQUIRES_VALIDATION` | 收到 JSON，但业务状态或结构不符合适配器；保留本地响应路径，不猜字段/URL，不算成功结果 |
| `SEARCH_VERIFIED` | normalize 已确认 `code=0`、data.list 与条目字段/猎聘岗位 URL 结构；records 是搜索卡片，不是完整 JD、精确关键词匹配或岗位开放证明 |

CLI 将验证后的卡片写入 search_leads，返回 `leads` 与导入数量；取得有来源的完整 JD 后才可提升为 jobs，按 [岗位导入契约](../.agents/skills/job-search/references/job-import-contract.md) 执行。`returned_count` 是首个响应页的规范化数量，返回线索受本地 limit 截取；不表示网站全部结果。

请求为 `POST https://open-agent.liepin.com/mcp/search-job`，仅发 jobName、可选 address 和 page=0；只取首页，30 秒超时、2 MiB 上限、不跟随重定向、不自动重试/批量轮询。原始响应与账号隔离缓存默认在 `data/private/liepin-search/`，可用 `CAREEROS_LIEPIN_CACHE` 指定；缓存 15 分钟且保留真实 fetched_at，`--refresh` 重新请求。响应可能含个人或平台数据，按私人材料处理，不自动读入整份聊天。

## 凭证配置

由用户本人在 [官方授权页](https://www.liepin.com/mcp/auth) 登录并生成 Token，当前有效期和权限以页面为准。凭证可能同时具备简历/投递权限，不能称 Token 本身只读；本项目仅调用搜索。授权页不是可直接配置的标准 MCP server URL。

主适配器只从环境变量读取，不依赖 PowerShell、官方 CLI 或全局 MCP/Skill。不要把 Token 放入聊天、终端历史、命令行参数、源码或普通配置文件。

Windows 可选用 DPAPI 辅助脚本：

```powershell
pwsh -NoProfile -File ./scripts/liepin.ps1 -Setup
pwsh -NoProfile -File ./scripts/liepin.ps1 -Status
pwsh -NoProfile -File ./scripts/liepin.ps1 -Query '产品经理' -Location '苏州' -Python '<已检查的解释器绝对路径>'
```

`-Setup` 隐藏输入并按当前 Windows 用户加密保存到 `data/private/liepin-token.dpapi`，不请求远端；`-Status` 只证明本地配置，不证明远端有效。查询在子进程临时注入 Token/启用变量并恢复原环境，不改 PATH；此查询仍须用户明确授权启用。脚本用 `-Refresh` 刷新，直接 CLI 用 `--refresh`。

项目不复用官方 CLI 的 setup，因为该流程会调用 get-resume。其他国内渠道和浏览器授权边界见 [中国渠道](CHINA_JOB_SOURCES.md)。
