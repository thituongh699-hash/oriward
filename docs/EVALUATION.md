# Evaluation and test manifest

本文列出应运行的检查，不把未在当前环境执行的检查写成已通过。

## 2026-10-18 导出收敛为纯格式转换

- `document-export` 现在只做格式转换：以已登记简历的当前内容为准，不写回任何记录；待事实确认的改版仍被拒绝。
- 结构化输入不得冒充简历：含 `个人简介/相关经历/教育经历/实习经历/工作经历/项目经历` 等标题时拒绝导出，必须走 `--resume-id`。
- 测试相应调整：移除 2 项旧用例、新增“结构化输入不得冒充简历”，含文档依赖的全量测试 **154/154 通过**。

## 2026-10-18 文档导出技能验收

- 新增 `document-export` 后，Windows 文档运行时（Python 3.12.14，含可选生成/提取库）全量 **144/144 通过**，其中 12 项是导出行为测试。新 Skill 的 `quick_validate.py` 验证通过。
- Ubuntu Linux 的核心运行时全量执行 144 项，其中 140 项通过、4 项因未安装可选文档依赖跳过。不能将其表述为 Linux 文档生成已实测通过；三个系统的可选后端 CI 已配置，尚待 Actions 执行。
- 测试覆盖：已登记简历的内容绑定、待确认改版拒绝、多个经历的归属顺序、未知结构拒绝、字形缺失拒绝、HTML 字符按原文显示、已有/并发产生的文件不覆盖，以及长表格分页。
- 虚构中文计划已生成 DOCX/PDF：PDF 3 页，经 Poppler 渲染并逐页检查，中文与特殊字符显示、文本提取和长表格续页正常；修复了标题与整张长表绑定导致的大片留白。
- DOCX 可重新打开，内容检查通过；规范 `render_docx.py` 因本机缺少 LibreOffice `soffice.exe` 失败，**DOCX 视觉验收未完成**。不将 PDF 的渲染结果当作 DOCX 的排版证据。导出 manifest 保持 `GENERATED_PENDING_VISUAL_REVIEW`，逐格式 QA 记录位于忽略目录 `outputs/document-export-qa-20261018/qa.json`。
- 发现既有缓存测试的文件修改时间在 NTFS 上可比 Python 微秒时钟略快；将缓存命中夹具固定在有效 TTL 内后完成全量回归，没有放宽生产缓存判断。

## 2026-10-18 启动与可移植性验证

- Windows / Python 3.14.2 与 WSL Ubuntu Linux / Python 3.14.4：分别运行全量单元测试，均为 **132/132 通过**。
- 两个环境均在临时数据库中完成 `doctor`、`init`、`twin status`、`context brief`，以及 18 次独立 CLI 调用的虚构招聘闭环；未联网、未投递、未修改真实资料。
- CI 已配置 Linux 三个 Python 版本及 Windows、macOS 作业；YAML 结构已校验。该配置尚未在 GitHub Actions 执行，本轮也未在 macOS 本机实测。
- Bash 辅助脚本仅做语法检查，Windows 凭证辅助脚本仅验证本地未配置状态；两者都不是首次使用主流程的前提。

## 2026-10-18 渠道补齐与统一记录增量验收

- `python -m unittest discover -s tests -v`：105/105 通过；新增 `tests/test_tracking.py` 8 项、`tests/test_official.py` 7 项。
- `python scripts/verify_channel_tracking.py --output outputs/channel-tracking-20261018`：隔离库、零网络、零投递。同一岗位在 3 个平台（zhiye/boss/liepin）归并为 1 组，`published_at`、JD、投递渠道、`applied_at`、时间线、日程、反馈落在同一记录。
- 同组第二次 `application prepare` 未被拦截，返回 `already_applied_in_group` 与 `decision=user_decides`；`pipeline.repeat_application_risk` 覆盖该组。
- 已有本地库 `data/private/careeros.sqlite3` 打开后 `applications` 自动补 `channel/apply_url/applied_at` 三列，`brief` 正常，未重建表。
- `official` 渠道边界有测试覆盖：拒绝 http、IP 字面量、localhost、带凭据 URL、非 443 端口与内网后缀；robots 禁止即失败；列表页或无 JD 页面不会被当成岗位导入。
- 未验证：真实雇主官网抓取、BOSS/智联端到端搜索、真实投递后的反馈回流。

## 2026-10-18 中国渠道与本地执行增量验收

- `python -m unittest discover -s tests -v`：79/79 通过；8 个项目 Skill 验证通过；`scripts/doctor.py` 环境检查通过。
- 隔离实例真实联网：职页“产品经理 / 上海”得到 3 条线索，一条完整 JD 成功转入岗位库；重复搜索 3 条均去重，命中缓存。
- 使用已保存真实 HTML 修复公司、城市及验证日期解析。再次运行缓存搜索/详情并禁止网络，调用数为 0；上海筛选匹配 1 条已入库岗位。
- 保留上游验证日期 `2026/08/09 09:12` 与本次抓取时间，不将聚合记录提升为当前开放状态。
- 新测试涵盖线索/岗位分离、站点域名与列表页防误入、时间跨时区比较、完整 JD/证据保留、文件摘要输出、缓存时间/robots/挑战页/响应大小等边界。
- 独立评审发现并修复旧查询缓存遇到较新线索导致整批失败的问题：本地搜索跳过旧观察、返回库内较新内容，同时继续处理其他结果。显式文件导入仍拒绝旧数据覆盖。compact 也保留未知来源字段（如资格、截止日期），只去除重复原始 HTML。
- 记录在 `outputs/china-search-local-20261018/verification.json`。该演示仅验证连接，关键词不是用户职业偏好；BOSS/智联没有直接本地搜索成功的声明。
- 没有量化实际模型 token 节省比例；确认本地 CLI 未新增模型调用、原始页面可留在本地、输出可只返回文件清单。

## 2026-10-18 前序招聘闭环验收

- Windows PowerShell 7、Python 3.14.2：`python -m unittest discover -s tests -q` **56/56 通过**；原基线为 10/10。
- 8 个项目 Skill 的 `quick_validate.py` 全部通过。另由独立评审检查了缺失硬资格、无公司资料时的评级边界；这不等同于真实招聘效果验证。
- `scripts/demo_hiring_loop.py --output outputs/hiring-loop-final-20261018`：18 次独立 CLI 调用通过；虚构案例 B→A，两版简历保留，关联反馈关闭。
- 独立审查发现的三项问题均已修复并加入回归覆盖：旧观察覆盖新 JD、无日期导入冒充新抓取、closed 岗位被 dossier 的 listed 状态提升为 A。
- 补充验证覆盖待确认改写、文件篡改、错误申请版本、过期复评关闭反馈，以及 Windows CLI 重定向输出 UTF-8。
- 本次只使用隔离测试/演示数据库，没有提交申请、上传个人简历或修改全局 Skills。

完整演示输入、输出和数据库保存在 `outputs/hiring-loop-final-20261018/`，不应作为真实候选人资料导入日常数据库。

## 自动化命令

```text
python -m unittest discover -s tests -v
```

预期覆盖：

- 8 个项目 Skill 的 frontmatter、名称与引用文件；
- 经历批准、证据状态、简历来源 ID 和应用状态机；
- CSV/JSON 岗位导入、同来源幂等、内容变化快照和 freshness；
- Greenhouse/Lever 映射、固定 HTTPS 主机、重定向/响应大小/超时边界；
- 初始分析模板保持 unknown，结构化分析校验精确 JD quote 和经历证据；
- `coverage_confirmed`、七阶段完整覆盖、A/B/C/D 与 `NEEDS_EVIDENCE`；
- exact resume/job hash、防止跨岗位和过期评审；
- actual/mock/hypothesis 反馈、application/exact resume 绑定；
- revision claim mapping、真人确认、独立复审和 feedback resolution 谱系。

Skill 结构验证：

由 Agent 使用宿主已有的 Skill 校验器（例如其 `quick_validate.py`），逐一校验 `.agents/skills/` 中的八个技能。校验器属于宿主开发工具，不是主程序依赖；其路径和调用方式由 Agent 根据环境确定，不在项目里硬编码。

该 validator 只证明 YAML/frontmatter 和基本结构，不证明工作流判断正确。

## 隔离端到端演示

```text
python scripts/demo_hiring_loop.py --output outputs/hiring-loop-demo-local
```

输出目录必须尚不存在，脚本不会覆盖既有文件。它使用完全虚构的数据和隔离数据库，依次执行 18 个 CLI 命令，覆盖岗位导入/快照、JD 分析、基线简历、七阶段 B 级评审、mock 反馈、保留原版的 revision、A 级独立复评和 feedback resolution。成功条件包括 B→A、两版简历都存在、open feedback 为 0。这个演示不开网络、不投递，也不证明真实岗位或录用效果。

## 2026-10-18 连接器冒烟证据

- Greenhouse `board=greenhouse`：公开 API 在一次 TLS EOF 后按既定边界单次重试成功；来源返回 19 个岗位，本次受限读取 1 个，description 长度 7,502 字符。
- Lever `board=lever`：官方 endpoint 返回 HTTP 200 和空列表；零记录是有效响应，不应误报连接失败。
- Lever 官方示例 `board=leverdemo`：受限读取 1 条，description 长度 6,625 字符。它是 demo 数据，只验证 adapter，不构成真实 vacancy 证据。

这些是指定日期的行为记录，不保证未来接口、board 内容或 TLS 状态。最终本地套件结果见上方；未列出的国内招聘平台没有经过 live 接通验证。

## 有意义的行为场景

| 场景 | 必须观察到的行为 |
| --- | --- |
| draft 含 “must” | 仅产生候选 hard gate，match 仍为 unknown |
| 缺少已批准证据 | `met` 被拒绝或保留 unknown/gap |
| 未知 hard gate | 不伪造等级，返回 `NEEDS_EVIDENCE`；若另有已知 D blocker，D 优先 |
| coverage 未确认 | 不能得到 A，最多 provisional B |
| 七阶段漏项/要求未覆盖 | review save 拒绝 |
| red finding 同份 review 标 resolved | 拒绝；改版/新证据后生成独立 review |
| structural finding + wording action | 仍保留 C/结构性限制 |
| 修改已评审简历文件 | 哈希检查拒绝 |
| 岗位内容改变 | 旧 analysis/review 过期；只改变 retrieved_at 不应制造内容变更 |
| actual feedback 绑定 READY_FOR_USER | 拒绝 |
| feedback 针对别的 resume/application | 拒绝 |
| 新措辞超出原事实逐字文本 | revision pending，确认前 `NEEDS_EVIDENCE` |
| 保存反馈 | application 状态和旧 grade 均不自动变化 |

## 人工质量评估

1. **JD 需求覆盖**：两名评审者独立标 hard gate/core/preferred；核查遗漏和精确 quote，不只比较措辞。
2. **证据追溯**：随机抽简历 bullet，沿 claim map 回到 experience action/outcome/evidence；目标是零虚构。
3. **红/蓝可执行性**：每个 finding 有证据且 action 能明确分到 wording/practice/evidence/retarget；结构问题未被包装成文字问题。
4. **招聘公平性**：pressure/background/competition 未使用受保护特征、未做未经授权调查、未虚构竞争者。
5. **来源质量**：核对 URL、日期、事实/推断拆分和开放状态；过期或不确定内容明确标注。
6. **反馈归因**：actual 反馈确实来自绑定 application；mock/hypothesis 未混同真实雇主意见。
7. **停止条件**：没有新证据时最多两轮，输出剩余风险或 retarget，而不是继续润色。

## 真实效果评估限制

申请转化率受岗位难度、候选人选择、经济周期、渠道和能力变化影响。少量历史样本不能证明某个措辞导致 offer。A–D 评审评价的是当前证据包在模拟阶段中的风险，不是校准录用概率。报告功能测试、数据质量和真实招聘结果时应分开呈现。
