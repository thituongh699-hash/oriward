# 浏览器职位发现

仅在选择连接浏览器搜索/阅读时加载。BOSS/智联的 HTTP/API 路径不可用时，继续正常页面操作；搜索计划不等于执行结果。字段与提升条件见 [job-import-contract.md](job-import-contract.md)。

## 操作与恢复

1. `jobs search --provider boss|zhilian ...` 或 `jobs browser-plan` 返回 `BROWSER_ACTION_REQUIRED`，CLI 没有自行浏览。
2. 读取宿主浏览器工具说明，复用已连接会话；接管用户标签须走工具的 claim 流程。不要复制 cookie、令牌或猜私有接口。
3. 观察当前页面，用可见搜索框和按钮操作，核对实际城市/筛选条件。新开标签后重新定位结果页；默认城市不等于用户偏好。
4. 读取小批可见卡片的标题、公司、城市、单岗链接和摘要。可基于已观察 DOM 批量读取可见卡片，不读隐藏状态，也不反复加载整页导航/账号栏。
5. 打开选中单岗，检查完整职责和要求。登录提示、遮挡、省略或未展开内容都是预览；掩码薪资不是 0，也不可猜测。
6. 登录/验证码需用户处理时保留 handoff 标签并报告页面。空白、节点失效或超时记录 `browser_error`，至多尝试一次受支持恢复；恢复后重新观察。不要无限刷新或把技术失败记为无岗位。
7. 保存观察回执和线索；只有实际读完完整单岗 JD 才提升。浏览器取可见内容，本地命令负责去重、校验、入库。

## 观察记录

`jobs browser-record --file <json>` 只存回执，不浏览也不创建岗位；`jobs browser-runs` 查历史。JSON 使用真实 `provider,query,location,source_url,observed_at,status,evidence,visible_count`。

状态：`search_verified|needs_login|needs_verification|browser_error|no_results`。`visible_count` 为 0..1000；`search_verified` 须大于 0，`no_results|browser_error` 须为 0。搜索可见不证明完整 JD 或仍在招聘；`no_results` 需要页面明确显示无结果。时间、数量、证据均来自实际观察。

浏览器线索用 `discovery_method:browser_ui` 和真实 `access_state`，标题绑定实际单岗 URL。`full_detail` 只能表示完整内容已读；提升同时需要 `read_method:browser_ui,access_state:full_detail,content_complete:true` 和完整字段/真实时间。

## 企业前端渲染页

雇主 ATS 为 SPA、普通读取只得空壳时，可选用公开页面渲染辅助：

```text
node scripts/read_rendered_page.mjs "https://<tenant>.jobs.feishu.cn/intern/?location=CT_xxx" page.json 14000
```

由 Agent 使用宿主支持的获准隔离浏览器，通过 `CDP_BASE` 提供端点；不假设可执行文件名。缺此能力时回到正常页面读取或授权导入，主程序无需辅助环境。输出包括可见文本和页面自身请求的 JSON，可用于核对列表和完整 JD，不能据此猜测绕过会话签名的直连接口。

只读公开页面，不登录、投递或复制凭证。城市/筛选来自用户 URL 或指令。快照中 `availability:listed` 不是雇主确认。记录获取方式 `retrieval_method` 用 `official_ats_api`（页面自身请求）或 `browser_ui`；不要与提升时的 `read_method` 混淆。

搜索授权不包含投递、沟通、收藏、关注或修改账号求职期望。一次故障不等于永久不支持；后续状态以重新观察为准。
