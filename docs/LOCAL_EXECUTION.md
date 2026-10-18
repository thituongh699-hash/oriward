# 本地执行与 token 节省

原则：确定性、可验证的处理使用本地 Python 和 SQLite；需要理解真实经历、判断要求及改写表达的步骤保留模型判断。项目 CLI 不调用任何模型 API，不引入第二个 LLM 服务，也不需要新增第三方 Python 依赖。

| 步骤 | 当前执行位置 | 质量边界 |
| --- | --- | --- |
| 职页搜索、完整 JD 获取、HTML 解析 | 本地 HTTP + HTMLParser | 单次有界、遵守 robots、挑战页停止 |
| 页面缓存、去重、URL/时间检查、快照 | 本地文件 + SQLite | 缓存不刷新来源时间，聚合信息不冒充官方开放状态 |
| 城市、关键词、排除项、结果数量筛选 | 本地 `jobs shortlist` | 是文字筛选，不是语义匹配或录用概率 |
| JD 初始模板、精确引文和证据引用校验 | 本地 `analysis draft/save` | 初始匹配 unknown，模型确认语义和完整覆盖 |
| 简历生成、版本/hash、申请包和状态校验 | 本地现有命令 | 新事实仍须本人确认 |
| 七阶段覆盖检查、A–D 规则计算 | 本地 `review save` | 模型提供有证据的评审输入，代码不猜经历含义 |
| 反馈分类、关联版本、改版和复审闭环 | 本地现有命令 | 真实/模拟/假设区分，不能靠自动改写消除硬缺口 |
| 要求理解、跨行业能力映射、措辞、模拟追问 | Agent | 这些步骤不能用关键词规则等价替代 |
| BOSS/智联公开索引发现 | 可用搜索工具或授权导入 | 本地适配尚未打通，不把搜索计划当结果 |

## 默认运行顺序

1. 先用本地搜索或已有库筛选最多 10 个候选，模型只读小列表。
2. 再获取选中岗位的完整 JD，缓存原始 HTML；不把完整网页、导航和脚本送入模型。
3. 分析/评审用 `--compact`：保留完整 JD、简历、经历证据、分析和既有问题/行动，去掉重复原始 HTML。未知来源字段也保留，避免漏掉资格或截止日期。不得为了省 token 截断硬要求或证据。
4. 批次结果和中间模板用全局 `--output` 保存。stdout 仅路径、字节数和 SHA-256。需要语义审阅时，再读取具体记录；不要立即把整个输出文件重新读进上下文。
5. 不重复调用模型做导入、模板拼接、打分规则、哈希或状态流转。没有新证据时，红蓝循环最多两轮；有数据变更则重新取 packet 复审。

```text
python -m careeros jobs search --query "产品经理" --location "上海" --limit 5
python -m careeros leads fetch --id 1
python -m careeros jobs shortlist --query "产品 数据" --location "上海" --exclude "外包" --limit 5
python -m careeros --output data/private/analysis-draft.json analysis draft --job-id 1
python -m careeros analysis packet --job-id 1 --compact
python -m careeros review packet --resume-id 1 --compact
```

示例 ID 由实际命令输出确定。`--output` 必须位于 domain 前；指定文件会被写入/覆盖。

搜索默认缓存 15 分钟，详情 24 小时；`--refresh` 请求重新读取，但原网站的验证时间仍保留。`CAREEROS_CACHE_DIR` 可指定缓存目录，默认位于当前数据库所在目录的 `cache/public-search`，不会混用另一数据库的默认缓存。

未承诺固定 token 节省百分比：实际效果取决于职位数量和对话使用方式。文件输出本身不会降低之后把全文读回模型的成本。本地 HTML 请求不消耗模型 token，但发起命令和查看摘要仍有对话开销。
