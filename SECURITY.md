# 安全策略

## 支持的版本

当前维护 `0.x` 系列，安全修复只进入最新版本。

## 上报漏洞

**请不要用公开 issue 报告安全问题。** 优先使用本仓库的 GitHub 私有漏洞上报（Security → Report a vulnerability / Private vulnerability reporting）。若该入口未开启，先开一个不含任何利用细节的 issue，仅请求一个私下沟通渠道。

上报时请说明：影响范围（哪些命令或模块）、复现所需的最小步骤、是否涉及凭证泄露或个人数据外泄、你建议的修复方向。**不要**附带真实简历、真实岗位库、招聘账号 Token 或任何第三方个人数据；如需示例，请用 `data/examples/` 的虚构记录或自行脱敏的最小样例。

## 安全边界（本项目承诺什么）

完整设计见 [docs/SECURITY.md](docs/SECURITY.md)。可对外承诺的部分：

- **不做未确认的外部动作**：不代投、不登录招聘账号、不联系招聘方、不绕过验证码、不自动购买或点击不可逆操作。`application record --status SUBMITTED` 只记账，不代表系统提交过任何内容。
- **凭证不进代码与输出**：猎聘 Token 通过环境变量在子进程内传递，本地以 Windows DPAPI 加密存放于被忽略的 `data/private/`；异常信息不回显服务端响应体，避免凭证随报错外泄。
- **个人数据默认留在本地**：`data/private/` 与 `outputs/` 被 Git 忽略；项目本身不向任何模型服务或第三方上传简历与经历。
- **外部内容视为数据**：JD、公司网页、招聘邮件、导入文件都可能含提示注入，只作为待分析材料，不作为指令执行。
- **推断不等于事实**：模型推断保持 `inferred` 状态，未经用户确认不得进入简历或"我是谁"的陈述。

## 已知的固有风险

- **Git ignore 不是加密。** 若机器被他人使用或磁盘未加密，`data/private/` 中的 SQLite 与缓存仍可被读取。
- **第三方平台条款优先于技术可行性。** `careeros/extras/` 下的可选扩展会调用第三方接口，合规责任在使用者；默认关闭，见 [docs/LIEPIN_INTEGRATION.md](docs/LIEPIN_INTEGRATION.md)。
- **抓取内容的时效性不由本项目保证。** `fresh` 只表示来源检索时间较近，不代表岗位仍开放。
- **A–D 评级是本地模拟结果**，恒带 `SIMULATED_HIRING_REVIEW_NOT_EMPLOYER_VERDICT`，不构成雇主决定、录用概率或对个人价值的判断。
