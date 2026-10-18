# 岗位与投递统一记录

目标：一个岗位只查一处，避免重复搜索、重复准备、重复投递，并让每次投递的渠道、日程和反馈都能追溯。核验日期 2026-10-18。

## 一条记录包含什么

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| 发布时间 `published_at` | 官方 JobPosting `datePosted`、导入文件、渠道 | 缺失即 `unknown`，不回填成抓取时间；`jobs card` 同时给出实际取值来源 |
| JD 全文 `description` | 完整单岗页面或授权导入 | 线索摘录永远不算 JD |
| 招聘渠道 `channels` | 同组各平台岗位 | 同一岗位在 BOSS/智联/猎聘/职页/官网各出现一次就记录一条 |
| 投递渠道 `application.channel` | 用户或渠道推断 | 记录实际投递发生在哪个平台 |
| 投递地址 `application.apply_url` | `prepare --apply-url` 或岗位 URL | 指向真正提交的那个页面 |
| 投递状态 `application.status` | 状态机 | `READY_FOR_USER → SUBMITTED → INTERVIEW → OFFER`，另有 `REJECTED/WITHDRAWN/DECLINED` |
| 投递时间 `applied_at` | 状态流转自动写入 | 只在 `SUBMITTED` 后存在，且必须有本人确认 |
| 日程节点 `application_events` | `application event` | 笔试、面试、跟进、offer 等，可带未来 `scheduled_at` |
| 后续反馈 `recruiting_feedback` | `feedback save` | 区分 `actual/mock/hypothesis`，绑定精确简历版本 |

命令入口：`jobs card`、`jobs group`、`pipeline`、`application timeline`、`application agenda`。

## 数据表

- `vacancy_groups`：`group_key` 唯一，保存归一化后的公司、岗位、城市。
- `job_group_members`：`job_id → group_id`，一个岗位只属于一个组。
- `application_events`：`application_id`、`kind`、`label`、`scheduled_at`、`occurred_at`、`data`。
- `applications`：新增 `channel`、`apply_url`、`applied_at`（旧库由 `db.migrate` 自动补列）。

`application_events` 由状态流转自动写入 `applied/interview/offer/rejection/withdrawal`，手工节点用于记录尚未发生的笔试面试安排。

## 多平台同岗归并规则

`group_key = sha256(normalize(company) + normalize(title) + normalize(location))[:24]`

- 公司：去掉 `有限公司/股份有限公司/集团` 等后缀与括号噪声。
- 岗位：去掉 `（急招）(热招)` 一类括号噪声与结尾的 `招聘/急聘`。
- 城市：取第一个城市词，去掉 `市/省/自治区` 后缀。

因此“北京三快在线科技有限公司 / 数据产品经理 / 上海市”与“北京三快在线科技 / 数据产品经理（急招） / 上海”会归为一组。

**归并只是候选提示**：同组不等于同一岗位，不同职级、不同团队、不同批次都可能落在同一组；跨城市不会归并。归并结果每次读岗位卡时按需重建，`jobs group --rebuild` 可强制重算。

## 重复投递：记录但不拦截

系统只做三件事：

1. `application prepare` 返回 `repeat_application_hints`，列出同组各平台渠道与 `already_applied_in_group`。
2. `jobs card` 给出 `repeat_application_risk.decision = user_decides`。
3. `pipeline` 汇总所有 `repeat_application_risk`。

系统不做的事：不拒绝第二次 `prepare`，不自动合并两个平台的申请，不把同组岗位标成已投递，不因为 `closed` 而删除历史记录。

判断依据仍由本人掌握，例如：同一雇主官网与 BOSS 是同一招聘流程（通常是重复），不同猎头代招同一岗位但走不同流程（可能不算），集团总部与子公司同名岗位（通常不算）。

## 数据缺口自查

`pipeline.data_gaps` 与 `jobs card.gaps` 会指出：

- `published_at_missing`：没有发布时间，无法判断新旧；
- `description_empty`：没有 JD，不能进入分析或评分；
- `application_channel_missing`：投递了但没记渠道，后续无法复盘渠道效果；
- `apply_url_missing`：投递地址缺失，无法回看提交的是哪一版。

这些缺口只报告，不猜测补全。

## 边界

- 不代投、不点击投递按钮、不登录、不上传简历；`SUBMITTED` 只记录本人确认过的事实。
- 聚合平台（职页/职友集/Careerjet）岗位的 `availability` 永远是 `unknown`，只有企业官网直招渠道可标 `listed`。
- `published_at` 与 `retrieved_at` 是两件事：前者是雇主发布时间，后者是本地读取时间。
