# Oriward 视觉素材

## Evidence Trails

空间以有节奏的留白容纳尚未确定的方向。点是一次经历，线是带着依据的联系；分岔保留可能性，回路表达反馈。构图以精细网格控制每个间隔，使复杂关系仍可被一眼辨认。

深墨蓝承载连续性，温白提供可阅读的纸面，浅绿色只标出当前值得关注的动作。颜色承担语义，装饰退到关系之后。每个色块与边缘都经过细致校准，让画面具有精工排版的秩序。

宽阔的无衬线品牌字、克制的中文和细小等宽标记建立尺度差。文字只留下问题与锚点，叙事交给路径。大师级执行体现在字距、基线、转折和空隙的反复打磨，而非元素数量。

视觉中心是一种可以修正的理解。轨迹抵达中心，又继续向外延伸；它不封闭成一个人的定义。整套素材以手工精校的节奏保持一致，并让每张画面在自己的尺度上成立。

## 文件

- `oriward-cover.png`：1600 × 900，GitHub README 首屏封面。
- `oriward-architecture.png`：1600 × 1080，Core / Agent / Skills / 反馈关系图。
- `oriward-poster.png`：1200 × 1600，项目介绍与分享海报。

所有图形由项目脚本绘制；架构图是概念关系示意，非产品界面截图。正文提供对应文字解释，便于检索和无障碍阅读。

从仓库根运行 `python scripts/render_readme_assets.py` 可复现，需额外安装 Pillow（仅素材生成使用，不是 Core 依赖）。默认字体取自 Windows 与本机 canvas-design 字体目录；其他环境用 `--font-dir`、`--cjk-font`、`--cjk-bold` 指定字体。字体文件不随仓库分发。

## GitHub 展示配置建议

项目显示名：**Oriward · 原向**。Oriward 由 Origin + Onward 构成：Origin 代表真实经历与价值观，Onward 代表继续探索方向、迈出下一步。名称对应可追溯、可纠正的 Career Twin Core，也表达从来路走向可能。

About 描述可直接复制：

> 面向在校生与应届生的本地求职成长工作台。以 Career Twin Core + Skills 连接自我认识、职业探索与求职行动，让每个建议有依据、每次反馈可追溯。

Topics 建议：`career`、`job-search`、`students`、`graduates`、`agent-skills`、`local-first`、`sqlite`、`python`。
