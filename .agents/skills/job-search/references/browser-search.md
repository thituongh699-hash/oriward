# BOSS / 智联浏览器搜索

用户要求必须保留这两个渠道。HTTP/公开 API 不通时，继续用已连接浏览器的正常页面操作，不要仅给搜索链接或索引计划后结束。

## 执行

1. `jobs search --provider boss|zhilian --query "..." --location "..."` 或 `jobs browser-plan` 返回 `BROWSER_ACTION_REQUIRED`。这是操作清单，CLI 自身没有启动浏览器或完成搜索。
2. 使用当前会话支持的浏览器工具，先读取其完整运行说明。复用已连接、已有登录态的用户浏览器；接管用户标签必须用工具提供的 claim 流程。不要复制 cookie、登录令牌或私有接口请求。
3. 读当前页面，使用可见搜索框/搜索按钮，选城市并核对实际选中的城市。默认定位城市不等于用户偏好。点击后若新开标签，检查标签列表再读取实际结果页。
4. 提取当前可见的小批量岗位标题、公司、城市、单岗链接和简短要求。不要把整页导航、账号栏、推荐历史反复送进上下文。基于已观察 DOM 可以批量读取可见卡片；不能读取隐藏状态或猜测后台接口。
5. 点击选中岗位验证详情地址和完整职责/任职要求。遇到“登录查看完整内容”、遮挡、省略或未展开，标为 `visible_preview`。薪资 `**-**` 不是 0，也不能猜测。
6. 登录/验证码需用户处理时保留 handoff 标签并说明具体页面；页面空白/节点持续失效记录 `browser_error`，先尝试一次受支持的恢复方式。用户恢复后重新观察再继续。不要重复无限刷新，也不要把技术失败等同于没有职位。
7. 本地记录观察、导入线索、完整 JD 提升。浏览器负责获取可见内容，本地负责去重、校验、入库和后续规则计算。

## 观察记录

`jobs browser-record --file <json>` 只保存观测回执，不自行浏览、不创建岗位；`jobs browser-runs` 查看历史。

```json
{"provider":"zhilian","query":"产品经理","location":"苏州","source_url":"https://www.zhaopin.com/jobs/","observed_at":"2026-10-18T03:00:00+00:00","status":"needs_login","evidence":"搜索框显示产品经理，城市苏州，列表可见；详情提示登录查看完整内容","visible_count":20}
```

这是格式示例，时间和数量必须来自实际观察。状态：`search_verified|needs_login|needs_verification|browser_error|no_results`。`search_verified` 只证明站内搜索结果可见，不证明完整 JD 已获取或雇主仍招人。`no_results` 必须页面明确显示无结果，不能从空白/加载失败推断。

`leads import --file <json>` 的浏览器记录使用 `discovery_method:browser_ui` 和 `access_state:visible_preview|full_detail`，其余同导入契约。标题必须绑定实际单岗 URL，不能用公司主页或搜索页代替。

## 企业自有 ATS（纯前端渲染）

部分雇主招聘站（如 `*.jobs.feishu.cn` 飞书招聘）是 SPA：HTML 里没有岗位数据，`curl`/WebFetch 只能拿到空壳，列表接口的 `_signature` 绑定浏览器会话，直连无效。此时用本地渲染读取，不要猜接口：

```text
node scripts/read_rendered_page.mjs "https://<tenant>.jobs.feishu.cn/intern/?location=CT_xxx" page.json 14000
```

这是可选的技术辅助路径。由 Agent 选择宿主可用的浏览器，在获准的隔离会话中准备 CDP 端点并通过 `CDP_BASE` 提供给脚本；不假设浏览器的可执行文件名或启动命令。没有该能力时使用正常页面读取或授权导入，主程序不要求安装这个辅助环境。

输出包含可见文本和页面自身发出的 JSON 响应（标题、城市、description、requirement、publish_time），既能核对列表，也能拿到完整 JD。

约束：

- 只读公开页面：不登录、不点击投递、不复制 cookie 或令牌；
- 城市与筛选条件必须来自用户给出的 URL 或明确指令，不能默认；
- 抓取结果是页面当时的快照，`availability=listed` 不等于雇主确认仍在招；
- 记录时把 `retrieval_method` 写成 `official_ats_api`（截获页面自身请求）或 `browser_ui`，不要写成 `official_site_read`。

读完完整 JD 后 `leads promote --id <id> --file <json>`：`read_method:browser_ui, access_state:full_detail, content_complete:true`，加完整标题、公司、description、URL 和真实 retrieved_at。只读预览时严禁设置这些完整标志；代码拒绝显式 preview 提升。

## 验证范围

2026-10-18：Edge 智联站内搜索返回产品经理岗位卡片，搜索/详情预览可读；当时页面仍有登录完整内容提示。BOSS 首页和已登录账号栏可读，但自动输入及搜索操作遭遇页面替换、节点失效、空白与超时，未证明端到端搜索成功。状态必须随着后续实际恢复更新，不能把一次故障写成永久不支持。

搜索/阅读不授权点击“立即投递”“立即沟通”、收藏、关注或修改账号求职期望。
