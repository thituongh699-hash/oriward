"""Run the entire CLI loop with fictional data in a new, isolated folder."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="虚构数据演示，不连接招聘站点，不投递简历")
    parser.add_argument("--output", required=True, help="New directory; never overwrites existing data")
    args = parser.parse_args()
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ, ORIWARD_DB=str(folder / "demo.sqlite3"),
                       ORIWARD_OUTPUT_DIR=str(folder / "resumes"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    commands = []

    def run(*argv):
        result = subprocess.run([sys.executable, "-m", "oriward", *map(str, argv)], cwd=ROOT,
                                env=environment, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{' '.join(map(str, argv))}: {result.stderr}")
        payload = json.loads(result.stdout)
        commands.append({"command": list(map(str, argv)), "result": payload})
        return payload

    def save(name, data):
        path = folder / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run("init")
    run("profile", "save", "--file", save("profile.json", {"display_name": "虚构候选人·演示专用"}))
    eid = run("experience", "add", "--file", save("experience.json", {
        "event": "虚构课程：公开数据清洗项目", "context": "仅用于软件验收，不代表用户经历",
        "actions": ["使用 Python 清洗公开数据并生成报告", "对缺失值规则进行验证并说明局限"],
        "outcomes": ["向课程小组展示数据处理方法"],
        "evidence": [{"claim": "完成数据清洗、规则验证和展示", "source": "虚构验收数据",
                      "status": "user_confirmed"}], "approved_for_resume": True}))['id']
    description = "使用 Python 完成数据清洗\n解释缺失值处理方法\n验证数据处理结果\n有团队展示经验优先"
    job = {"source": "fictional-demo", "source_id": "analyst-1", "title": "数据分析助理（虚构）",
           "company": "演示公司（不存在）", "description": description, "retrieved_at": timestamp,
           "url": "https://example.invalid/careers/demo", "availability": "listed"}
    jid = run("jobs", "import", "--json", save("jobs.json", [job]))["job_ids"][0]
    run("jobs", "snapshots", "--id", jid)
    draft = run("analysis", "draft", "--job-id", jid)
    for requirement in draft["requirements"]:
        requirement.update(match="met", experience_ids=[eid], rationale="虚构经历包含对应清洗、验证、展示证据")
    draft.update(unknowns=[], coverage_confirmed=True, company_context=[{
        "url": job["url"], "retrieved_at": timestamp, "fact": "验收夹具假定岗位当前开放，非真实职位",
        "inference": "", "availability": "listed"}])
    run("analysis", "save", "--file", save("analysis.json", draft))
    resume = run("resume", "build", "--job-id", jid, "--experience-ids", eid, "--headline", job["title"])
    packet = run("review", "packet", "--resume-id", resume["id"])
    review = packet["review_template"]
    for stage in review["stages"].values():
        stage.update(verdict="pass", rationale="虚构模拟：逐项核对已知 JD 与经历", requirement_ids=[r["id"] for r in draft["requirements"]])
    review["stages"]["technical"].update(verdict="risk", rationale="经历有依据，但缺失值处理的回答需要演练",
        questions=["为什么采用该缺失值策略？如何验证它没有扭曲结果？"])
    review["red_findings"] = [{"id": "R1", "stage": "technical", "severity": "preparation",
        "issue": "技术回答尚未完成验证", "evidence": "本次模拟尚未完成技术问答",
        "requirement_ids": [draft["requirements"][1]["id"]]}]
    review["blue_actions"] = [{"finding_id": "R1", "type": "practice", "action": "演练处理规则、替代方案和验证方法"}]
    before = run("review", "save", "--file", save("review-before.json", review))
    feedback = run("feedback", "save", "--file", save("feedback.json", {
        "job_id": jid, "resume_id": resume["id"], "kind": "mock", "stage": "technical", "outcome": "pass",
        "observation": "虚构演练：能解释缺失值策略、替代方案和验证结果", "source": "虚构模拟面试验收",
        "observed_at": timestamp, "actions": [{"category": "wording", "text": "将已有规则验证事实前置"},
            {"category": "practice", "text": "复评技术回答能否支持简历表述"}]}))
    run("feedback", "plan", "--job-id", jid)
    texts = ["对缺失值规则进行验证并说明局限", "使用 Python 清洗公开数据并生成报告", "向课程小组展示数据处理方法"]
    revised = run("resume", "revise", "--file", save("revision.json", {
        "base_resume_id": resume["id"], "review_id": before["id"], "feedback_ids": [feedback["id"]],
        "reason": "按模拟反馈重排已确认事实，前置验证方法", "sections": [{"experience_id": eid,
            "bullets": [{"text": text, "source_texts": [text]} for text in texts]}]}))
    packet = run("review", "packet", "--resume-id", revised["id"])
    review = packet["review_template"]
    for name, stage in review["stages"].items():
        stage.update(verdict="pass", rationale=f"虚构复评：{name} 已核验；技术演练依据 feedback {feedback['id']}",
                     requirement_ids=[r["id"] for r in draft["requirements"]])
    after = run("review", "save", "--file", save("review-after.json", review))
    run("feedback", "resolve", "--id", feedback["id"], "--review-id", after["id"], "--note", "已完成已知事实重排与虚构面试复评")
    history = run("resume", "history", "--id", revised["id"])
    plan = run("feedback", "plan", "--job-id", jid)
    assert before["grade"] == "B" and after["grade"] == "A" and plan["open_count"] == 0 and len(history) == 2
    save("commands.json", commands)
    labels = {"ats": "ATS 初筛", "hr": "HR 面", "hiring_manager": "用人经理", "technical": "专业技术面",
              "pressure": "压力与追问", "background": "背景核验", "competition": "竞争力比较"}
    rows = "\n".join(f"| {label} | {'需演练' if stage == 'technical' else '模拟通过'} | 模拟通过 |" for stage, label in labels.items())
    report = f"""# 求职闭环演示验收

**全部为虚构数据，不是用户的简历评级或真实岗位。不发送任何申请。**

已通过 {len(commands)} 次独立 CLI 调用，完成来源导入、JD 分析、简历生成、七阶段红蓝评审、模拟面试反馈、修订、复评和反馈关闭。

## 评审结果

| 环节 | 原版 | 修订与演练后 |
| --- | --- | --- |
{rows}

模拟评级：**B → A**。变化原因是补充了虚构演练结果并重新审视全部环节；不是润色自动加分。
A级仅表示已知要求与本次模拟一致，不保证录用。硬条件缺口不能靠改写消除。

- 岗位 ID：{jid}；来源快照保存在演示数据库。
- 简历：原版 {resume['id']} → 修订版 {revised['id']}，原版未覆盖。
- 红队问题：技术问答准备不足。
- 蓝队动作：演练处理规则、替代方案、验证方法，前置已有事实。
- 反馈 {feedback['id']} 关联修订版与复评 {after['id']}，剩余未关闭反馈：{plan['open_count']}。
- [原版简历](resumes/{Path(resume['path']).name}) / [修订简历](resumes/{Path(revised['path']).name})
- [逐条 CLI 输入输出](commands.json) / [修订内容及证据](revision.json)

此演示没有联网，不验证岗位真实性；联网连接器测试结果另见项目验收记录。
"""
    (folder / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"ok": True, "commands": len(commands), "before": before["grade"], "after": after["grade"],
                      "report": str(folder / "REPORT.md"), "db": str(folder / "demo.sqlite3")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
