"""Verify persistent Career Twin decisions through independent CLI processes.

All data and simulated confirmations are fictional. Never opens personal state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New directory; refuses to overwrite")
    args = parser.parse_args()
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ, CAREEROS_DB=str(folder / "demo.sqlite3"),
                       CAREEROS_OUTPUT_DIR=str(folder / "resumes"),
                       PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    commands = []

    def save(name, data):
        path = folder / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        return str(path)

    def run(*argv, error=None):
        result = subprocess.run([sys.executable, "-m", "careeros", *map(str, argv)],
                                cwd=ROOT, env=environment, capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        entry = {"command": list(map(str, argv)), "returncode": result.returncode}
        commands.append(entry)
        if error:
            entry["stderr"] = result.stderr
            if result.returncode == 0 or error not in result.stderr:
                raise AssertionError(entry)
            return None
        if result.returncode:
            raise RuntimeError(f"{argv}: {result.stderr}")
        entry["result"] = json.loads(result.stdout)
        return entry["result"]

    def check(condition, message):
        if not condition:
            raise AssertionError(message)

    try:
        check(run("init")["schema_version"] == 4, "schema v4")
        run("profile", "save", "--file", save("profile.json", {
            "display_name": "职业孪生验收候选人（虚构）", "values": ["可迁移能力"],
            "hard_constraints": ["不接受长期出差"]}))
        eid = run("experience", "add", "--file", save("experience.json", {
            "event": "虚构 SQL 课程项目", "context": "软件测试夹具，不是用户经历",
            "actions": ["使用 SQL 清洗公开数据"], "outcomes": ["完成课程展示"],
            "approved_for_resume": True,
            "evidence": [{"claim": "使用 SQL 清洗数据", "source": "虚构验收材料",
                          "status": "user_confirmed"}],
            "inferred_skills": [{"name": "SQL", "reason": "虚构项目包含清洗操作"}]}))["id"]
        run("twin", "sync-legacy")
        check(run("twin", "sync-legacy")["assertions_created"] == 0, "idempotent bridge")
        skill = run("belief", "list", "--type", "skill_hypothesis")[0]["id"]
        constraint = run("belief", "list", "--type", "constraint")[0]["id"]
        run("belief", "confirm", "--id", skill, "--note", "虚构测试用户确认具体项目动作")
        run("belief", "confirm", "--id", constraint, "--note", "虚构测试用户明确硬约束")
        gid = run("goal", "add", "--file", save("goal.json", {
            "title": "探索数据分析方向（虚构）", "priority": 1, "status": "active",
            "owner": "user", "time_budget_hours": 2, "rationale": "先低成本验证迁移方向"}))["id"]
        jid = run("jobs", "import", "--json", save("jobs.json", [{
            "source": "fictional-demo", "source_id": "twin-analyst", "title": "数据助理（虚构）",
            "company": "不存在的验收公司", "description": "使用 SQL 清洗数据，无长期出差要求",
            "availability": "listed", "url": "https://example.invalid/twin-demo",
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]))["job_ids"][0]
        run("pipeline", "update", "--job-id", jid, "--status", "shortlisted", "--goal-id", gid,
            "--reason", "虚构夹具：需结合用户证据进一步验证")
        aid = run("action", "propose", "--file", save("action.json", {
            "title": "整理 SQL 项目案例（虚构）", "source_type": "job", "source_id": jid,
            "action_type": "prepare", "effort_hours": 1,
            "suggestion_reason": "SQL 项目对应岗位清洗任务，先用一小时验证方向"}))["id"]
        check(run("action", "list")["review"][0]["id"] == aid, "unverified constraint gates advice")
        factors = {name: {"status": "supports", "reason": reason} for name, reason in {
            "goal": "服务用户的数据分析探索目标", "preference": "积累可迁移的能力证据",
            "job": "虚构岗位明确要求 SQL 清洗", "deadline": "先在本周准备，岗位期限仍需查证",
            "capability": "已确认的 SQL 项目与操作", "cost": "本周两小时预算内安排一小时"}.items()}
        factors["deadline"]["status"] = "not_applicable"
        factors["capability"].update(assertion_ids=[skill], experience_ids=[eid])
        factors["cost"]["planned_weekly_hours"] = 1
        decision = {"action_id": aid, "reason": "真实操作证据与任务相符，先做低成本方向验证",
                    "factors": factors, "alternatives": [
                        {"title": "立即制作完整作品集", "reason": "投入较大，先验证方向"}]}
        run("decision", "record", "--file", save("incomplete-decision.json", decision), error="every current")
        decision["constraint_checks"] = [{"assertion_id": constraint, "status": "satisfied",
                                          "reason": "虚构 JD 明确无长期出差要求"}]
        first = run("decision", "record", "--file", save("decision-v1.json", decision))
        check(first["assessment"]["status"] == "eligible", "fully assessed plan")
        frozen = run("decision", "show", "--id", first["id"])["context"]
        run("decision", "outcome", "--id", first["id"], "--kind", "accepted", "--note", "虚构选择",
            error="human-confirmed")
        run("decision", "outcome", "--id", first["id"], "--kind", "accepted", "--note",
            "虚构测试用户选择先做小案例，因为临近期末", "--human-confirmed")
        run("goal", "update", "--id", gid, "--time-budget-hours", 3,
            "--note", "虚构情境：考试结束，可用时间增加")
        old = run("decision", "show", "--id", first["id"])
        check(old["context"] == frozen and old["current_assessment"]["status"] == "review",
              "old reasoning frozen and reassessment required")
        decision["reason"] = "考试结束后重新核实目标与岗位，仍先做一小时案例"
        second = run("decision", "record", "--file", save("decision-v2.json", decision))
        check(second["previous_id"] == first["id"], "decision chain")
        brief = run("context", "brief", "--max-chars", 20000)
        check(all(key in brief for key in ("who_am_i", "who_could_i_become", "where_i_am_now", "what_next", "why")),
              "all five questions")
        check(brief["what_next"]["actions"][0]["decision_id"] == second["id"], "brief decision link")
        artifact = folder / "case-study.md"
        artifact.write_text("# 虚构验收产物\nSQL 清洗案例说明，仅用于验证结果记录。\n", encoding="utf-8", newline="\n")
        run("action", "complete", "--id", aid, "--evidence", artifact)
        history = run("decision", "history", "--action-id", aid)["versions"]
        check(len(history) == 2 and history[1]["events"][-1]["kind"] == "completed", "completion event")
        check(len(run("goal", "history", "--id", gid)["versions"]) == 2, "goal change history")
        run("belief", "retract", "--id", skill, "--reason", "虚构测试：原先能力判断需撤回")
        run("twin", "sync-legacy")
        check(not run("belief", "list", "--type", "skill_hypothesis"), "legacy cannot revive retracted skill")
        check(len(run("belief", "history", "--id", skill)["versions"]) >= 1, "retraction retains history")
        save("result.json", {"ok": True, "commands": len(commands), "action_id": aid,
                             "decision_ids": [first["id"], second["id"]], "db": str(folder / "demo.sqlite3")})
        print((folder / "result.json").read_text(encoding="utf-8"))
    finally:
        save("commands.json", commands)


if __name__ == "__main__":
    main()
