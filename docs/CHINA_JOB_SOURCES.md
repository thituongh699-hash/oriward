# 中国职位渠道接入

核验日期：2026-10-18。检索/抓取成功与职位仍开放分开记录。

| 渠道 | 本次实际状态 | 项目支持 | 可记为投递渠道 |
| --- | --- | --- | --- |
| 企业官网直招 official | 本地单页只读解析已实现（JSON-LD `JobPosting` 优先，HTML 兜底） | `official plan` / `official fetch`，解析 JD、发布时间、投递入口 | 是 |
| 职页 zhiye.page | 本地公开搜索和详情获取成功 | 本地适配器、缓存、线索入库、完整 JD 转入岗位库 | 否 |
| BOSS 直聘 | 公开搜索索引能发现列表；robots 限制查询参数抓取 | 索引线索/授权完整 JD 导入；浏览器渠道，没有直接搜索或登录态抓取 | 是 |
| 智联招聘 | 公开索引能发现详情；本地请求遇到安全验证 | 索引线索/授权完整 JD 导入；浏览器渠道，没有绕过验证 | 是 |
| 猎聘 | 官方搜索 API 已实测（需 Token） | **可选扩展，默认关闭**（`CAREEROS_ENABLE_LIEPIN=1` 开启）；只返回搜索卡片，完整 JD 需人工读取后导入 | 是 |
| 前程无忧 | 未实测本地直接查询 | 渠道目录、公开检索计划、授权导入 | 是 |
| 职友集 | 官方开放 XML 是供其收录的输入格式 | 发现入口；不是已接入的职位读取 API | 否（仅发现） |
| Careerjet 中国 | 官方提供发布商职位搜索 API | 待 API key 配置和授权验证；尚无已交付适配器 | 否 |
| 国家大学生就业服务平台、中国公共招聘网 | 官方就业信息入口 | 搜索计划/授权导入；未声称存在可用公共 API | 是 |

职页适合企业官网岗位聚合发现，不保证覆盖所有城市、行业或 BOSS/智联的信息。搜索当前只取首个结果页，返回 `scope=first_public_result_page`；`has_more` 仅表示该页解析结果超过请求数量，不代表网站总分页数量。需覆盖更多岗位时应主动改变检索条件，不能将本地结果当作全网全集。

官方渠道是唯一能同时证明“岗位由雇主发布”和“投递入口属于雇主”的来源。它只读一个单岗页面：要求 HTTPS、公共域名、robots 允许、2 MB 与 15 秒上限、同主机重定向，拒绝 IP 字面量、凭据、非 443 端口与内网后缀。页面没有可读 JD 时明确失败，不会把列表页当岗位。`jobs route --provider official` 给出从公司名到投递的完整步骤；`jobs channels` 给出每个渠道的 `access`、`supports`、`apply_channel`。


## 可复现实测

隔离数据库：`outputs/china-search-local-20261018/careeros.sqlite3`；记录：同目录 `verification.json`。

以“产品经理 / 上海”为连接测试（不是用户求职偏好）：搜索得到 3 条线索，重复搜索命中缓存且重复计数为 3，选中一条抓取完整 JD 并入库。页面显示的上游验证日期明显早于本次读取日期，因此职位开放状态保持 unknown。没有提交申请或读取个人简历。

## 方案调研及选择

- [职页搜索](https://zhiye.page/jobs)、[robots](https://zhiye.page/robots.txt)、[机器人说明](https://zhiye.page/bot)：实读公开 HTML，使用标准库实现固定主机、有界抓取和 HTML 解析。保留官网链接，但不自动追踪。
- [BOSS robots](https://www.zhipin.com/robots.txt)：本次读取含查询参数抓取限制。因此不采用直接查询抓取。
- [智联官网](https://www.zhaopin.com/)：公开索引存在可读 JD，本地入口请求遇到安全验证。索引摘要不能当完整 JD，缓存抓取日期不能当雇主开放确认。
- [Careerjet 官方 API 文档](https://www.careerjet.cn/partners/api)：说明 v4/query、发布商密钥、user_ip 与 user_agent。未提供密钥，未做实际 API 联调。
- [职友集开放收录说明](https://about.jobui.com/?type=open)：XML 为信息提供者提交格式，不能据此推断有公开读取接口。
- [zhilian-recruitment-fastapi](https://github.com/hyhang915/zhilian-recruitment-fastapi)：阅读 README 和实际 service.py，借鉴查询与字段归一化分离。其调用前端接口的实现不等于官方公共接口，本项目未采用。
- [job-harvest-hub](https://github.com/Simon-in/job-harvest-hub)：README 描述 FastAPI/Playwright/SQLite，说明部分源不可用和 JD 获取边界。仅核验代码库说明，未部署验证，不把作者声称支持当本项目可用。
- [国家大学生就业服务平台](https://www.ncss.cn/)、[中国公共招聘网](https://job.mohrss.gov.cn/)：列为应届生及公共就业补充渠道。

获得足够架构依据后停止调研：采用轻量本地适配器和独立线索表，不部署浏览器抓取服务器，不新增模型调用服务。

## 本地边界

请求限时 15 秒、响应最多 2 MB、同进程请求间隔至少 2 秒、固定 HTTPS 主机、同主机重定向、robots 检查。机器人策略无法读取、挑战页或页面结构不符时明确失败。缓存命中沿用真实读取时间。多个独立 CLI 进程不共享限速锁，请顺序运行抓取命令。

索引线索保存在独立 `search_leads` 表，必须获得完整单岗 JD 才可提升为 `jobs`。聚合详情的 `availability` 保持 unknown；官网 URL、聚合页面 URL、上游验证标签、抓取时间分别保存。
